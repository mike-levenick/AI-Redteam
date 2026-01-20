#!/usr/bin/env python3

import sys
import os
import json
import time
import socket
from datetime import datetime
from anthropic import Anthropic
import openai
import requests
from system_prompt import get_system_prompt, get_flag_for_stage
from knowledge_base import KnowledgeBase

class LLMShell:
    # Model configuration - set to True for Sonnet, False for Haiku
    USE_SONNET = False
    # Debug mode - set to True to see tool calls and results in stderr
    DEBUG_MODE = False
    # Maximum conversation history messages to keep (prevents unbounded context growth)
    MAX_HISTORY = 14

    def __init__(self):
        self.assistant_name = "AI"
        self.location = "The Cloud"
        self.session_id = f"session_{int(time.time())}"

        # Capture the user's name from SSH and title-case it
        raw_name = os.getenv('USER', 'unknown_user')
        self.user_name = raw_name.title()

        # Set model based on configuration
        if self.USE_SONNET:
            self.claude_model = "claude-sonnet-4-5-20250929"
        else:
            self.claude_model = "claude-haiku-4-5-20251001"

        # Initialize LLM clients
        self.anthropic_client = None
        self.openai_client = None
        self.ollama_host = None
        
        self.setup_llm_clients()
        self.log_session_start()
        
        # Session state
        self.known_visitors = []
        self.conversation_history = []  # Track full conversation for LLM context
        self.stage = 1  # You can track puzzle progress

        # Generate system prompt based on current stage
        # Include user name so the AI always knows who it's talking to
        self._update_system_prompt()

        # Initialize knowledge base for RAG
        # Use local path if running locally, Docker path if in container
        knowledge_dir = os.getenv('KNOWLEDGE_DIR', '/app/knowledge')
        if not os.path.exists(knowledge_dir):
            # Fallback to local directory structure
            script_dir = os.path.dirname(os.path.abspath(__file__))
            knowledge_dir = os.path.join(script_dir, 'knowledge')

        self.knowledge_base = KnowledgeBase(knowledge_dir=knowledge_dir)

        # Define the search tool for AI
        self.search_tool = {
            "name": "search_knowledge",
            "description": "Search the knowledge base for information. Use this tool when you need to look up specific topics, terms, or data that may be stored in the knowledge base.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The term or topic to search for. Try specific terms first, then broader terms if needed."
                    }
                },
                "required": ["query"]
            }
        }

    def _update_system_prompt(self):
        """Regenerate system prompt for current stage"""
        self.system_prompt = get_system_prompt(user_name=self.user_name, stage=self.stage)

    def _get_available_tools(self):
        """Return list of tools available for the current stage"""
        if self.stage == 3:
            return [self.search_tool]
        return []

    def _check_flag_submission(self, flag_input):
        """Check if user submitted a valid flag and advance stage if so"""
        current_flag = get_flag_for_stage(self.stage)
        submitted_flag = flag_input.strip()

        if current_flag and submitted_flag == current_flag:
            if self.stage < 5:
                old_stage = self.stage
                self.stage += 1
                self._update_system_prompt()
                self.conversation_history = []  # Clear history for new stage
                return True, old_stage
            else:
                # Stage 5 completed - game won!
                return True, 5
        return False, None

    def setup_llm_clients(self):
        """Initialize available LLM clients"""
        try:
            if os.getenv('ANTHROPIC_API_KEY'):
                self.anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                # print("✅ Claude initialized", file=sys.stderr)
                
            if os.getenv('OPENAI_API_KEY'):
                self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                # print("✅ OpenAI initialized", file=sys.stderr)
                
            if os.getenv('OLLAMA_HOST'):
                self.ollama_host = os.getenv('OLLAMA_HOST')
                # Test Ollama connection
                try:
                    response = requests.get(f"{self.ollama_host}/api/tags", timeout=2)
                    if response.status_code == 200:
                        pass
                        # print("✅ Ollama initialized", file=sys.stderr)
                    else:
                        self.ollama_host = None
                except:
                    self.ollama_host = None
                    
        except Exception as e:
            print(f"Error initializing LLM clients: {e}", file=sys.stderr)

    def log_session_start(self):
        """Log session start"""
        try:
            os.makedirs("/app/logs", exist_ok=True)
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "event": "session_start",
                "client_ip": os.getenv("SSH_CLIENT", "unknown").split()[0] if os.getenv("SSH_CLIENT") else "unknown"
            }
            
            with open(f"/app/logs/llm_shell.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except:
            pass

    def log_command(self, user_input, response):
        """Log conversation with the AI"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "event": "chat",
                "user_input": user_input,
                "ai_response": response,
                "stage": self.stage
            }
            
            with open(f"/app/logs/llm_shell.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except:
            pass

    def _build_messages_with_cache(self):
        """Build messages list with caching strategy for conversation history"""
        messages_to_send = []
        for i, msg in enumerate(self.conversation_history):
            # If we have at least 4 messages, add cache control to the second-to-last message
            # This caches everything except the current user input
            if len(self.conversation_history) >= 4 and i == len(self.conversation_history) - 2:
                # Only add cache_control to simple string messages
                # Tool use messages already have proper content structure
                if isinstance(msg["content"], str):
                    new_msg = {
                        "role": msg["role"],
                        "content": [
                            {
                                "type": "text",
                                "text": msg["content"],
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    }
                else:
                    # For structured content (tool use/results), add cache_control to last block
                    content_copy = msg["content"].copy() if isinstance(msg["content"], list) else msg["content"]
                    if isinstance(content_copy, list) and len(content_copy) > 0:
                        # Add cache_control to the last content block
                        content_copy[-1]["cache_control"] = {"type": "ephemeral"}
                    new_msg = {"role": msg["role"], "content": content_copy}
            else:
                # Regular message format
                new_msg = {"role": msg["role"], "content": msg["content"]}

            messages_to_send.append(new_msg)
        return messages_to_send

    def _execute_tool(self, tool_name, tool_input):
        """Execute a tool call and return the result"""
        if tool_name == "search_knowledge":
            query = tool_input.get("query", "")
            # Allow restricted content access in stage 3 for the tool-based attack
            allow_restricted = (self.stage == 3)

            # Get raw results for debug info
            raw_results = self.knowledge_base.search(query, max_results=3, max_chars=1500, allow_restricted=allow_restricted)

            if self.DEBUG_MODE:
                print(f"[DEBUG] Search found {len(raw_results)} results", file=sys.stderr)
                for i, (score, title, _, _) in enumerate(raw_results):
                    print(f"[DEBUG]   {i+1}. '{title}' (score: {score})", file=sys.stderr)

            result = self.knowledge_base.get_context(query, max_chars=1500, allow_restricted=allow_restricted)
            if result:
                return result
            else:
                return "No relevant information found in the archives for this query. Try different search terms."
        return "Unknown tool"

    def _smart_truncate_history(self):
        """Truncate history while keeping tool_use/tool_result pairs together"""
        if len(self.conversation_history) <= self.MAX_HISTORY:
            return

        # Start from MAX_HISTORY messages back
        start_idx = len(self.conversation_history) - self.MAX_HISTORY

        # Check if we're starting on a tool_result - if so, back up to include its tool_use
        while start_idx > 0:
            msg = self.conversation_history[start_idx]
            content = msg.get("content", "")

            # Check if this is a tool_result message
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                    # Back up one more to include the assistant's tool_use
                    start_idx -= 1
                    continue
            break

        self.conversation_history = self.conversation_history[start_idx:]

    def query_llm(self, prompt):
        """Query the configured LLM with tool-based RAG"""

        # Keep conversation manageable - trim while keeping tool pairs together
        self._smart_truncate_history()

        # Use current system prompt
        system_prompt = self.system_prompt

        # Add user message to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": prompt
        })

        try:
            # Try Anthropic Claude first with retry logic
            if self.anthropic_client:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Build messages with caching
                        messages_to_send = self._build_messages_with_cache()

                        # Get available tools for current stage
                        available_tools = self._get_available_tools()

                        # First call: non-streaming to check for tool use
                        api_params = {
                            "model": self.claude_model,
                            "max_tokens": 1000,
                            "system": [
                                {
                                    "type": "text",
                                    "text": system_prompt,
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ],
                            "messages": messages_to_send
                        }

                        # Only add tools if there are any available
                        if available_tools:
                            api_params["tools"] = available_tools

                        response = self.anthropic_client.messages.create(**api_params)

                        # Debug: show token usage and cache info
                        if self.DEBUG_MODE:
                            usage = response.usage
                            print(f"\n[DEBUG] Tokens - Input: {usage.input_tokens}, Output: {usage.output_tokens}", file=sys.stderr)
                            if hasattr(usage, 'cache_creation_input_tokens'):
                                print(f"[DEBUG] Cache - Write: {usage.cache_creation_input_tokens}, Read: {usage.cache_read_input_tokens}", file=sys.stderr)

                        # Handle tool use in a loop (allows multiple searches per turn)
                        max_tool_calls = 3  # Prevent infinite loops
                        tool_calls = 0
                        printed_prefix = False  # Track if we've already printed AI:

                        while response.stop_reason == "tool_use" and tool_calls < max_tool_calls:
                            tool_calls += 1

                            # Print any text content that came before the tool call
                            # (e.g., "Let me search for that...") with fake streaming
                            for block in response.content:
                                if hasattr(block, 'text') and block.text:
                                    if not printed_prefix:
                                        print("\nAI: ", end="", flush=True)
                                        printed_prefix = True
                                    # Fake streaming effect for pre-tool text
                                    for char in block.text:
                                        print(char, end="", flush=True)
                                        time.sleep(0.01)

                            # Find ALL tool use blocks (model may request multiple parallel searches)
                            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

                            if not tool_use_blocks:
                                break

                            # Execute all tool calls and collect results
                            tool_results = []
                            for tool_use_block in tool_use_blocks:
                                # Debug: show tool call
                                if self.DEBUG_MODE:
                                    print(f"\n[DEBUG] Tool call #{tool_calls}: {tool_use_block.name}({tool_use_block.input})", file=sys.stderr)
                                    print(f"[DEBUG] Tool use ID: {tool_use_block.id}", file=sys.stderr)

                                # Execute the tool
                                tool_result = self._execute_tool(tool_use_block.name, tool_use_block.input)

                                # Debug: show result preview
                                if self.DEBUG_MODE:
                                    preview = tool_result[:100] + "..." if len(tool_result) > 100 else tool_result
                                    print(f"[DEBUG] Result: {preview}", file=sys.stderr)

                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_block.id,
                                    "content": tool_result
                                })

                            # Add the assistant's tool request to history
                            # Convert SDK objects to dicts for serialization
                            content_dicts = [block.model_dump() for block in response.content]

                            # Debug: verify the tool_use IDs in stored content
                            if self.DEBUG_MODE:
                                for cd in content_dicts:
                                    if cd.get('type') == 'tool_use':
                                        print(f"[DEBUG] Storing assistant tool_use ID: {cd.get('id')}", file=sys.stderr)

                            self.conversation_history.append({
                                "role": "assistant",
                                "content": content_dicts
                            })

                            # Add ALL tool results in a single user message
                            self.conversation_history.append({
                                "role": "user",
                                "content": tool_results
                            })

                            # Rebuild messages and check if model wants another tool call
                            messages_to_send = self._build_messages_with_cache()

                            # Debug: show message structure before sending
                            if self.DEBUG_MODE:
                                print(f"[DEBUG] Sending {len(messages_to_send)} messages:", file=sys.stderr)
                                for j, m in enumerate(messages_to_send):
                                    content_preview = str(m.get('content', ''))[:50]
                                    print(f"[DEBUG]   {j}. {m['role']}: {content_preview}...", file=sys.stderr)

                            api_params = {
                                "model": self.claude_model,
                                "max_tokens": 1000,
                                "system": [
                                    {
                                        "type": "text",
                                        "text": system_prompt,
                                        "cache_control": {"type": "ephemeral"}
                                    }
                                ],
                                "messages": messages_to_send
                            }

                            if available_tools:
                                api_params["tools"] = available_tools

                            response = self.anthropic_client.messages.create(**api_params)

                            # Debug: show token usage
                            if self.DEBUG_MODE:
                                usage = response.usage
                                print(f"[DEBUG] Tokens - Input: {usage.input_tokens}, Output: {usage.output_tokens}", file=sys.stderr)
                                if hasattr(usage, 'cache_creation_input_tokens'):
                                    print(f"[DEBUG] Cache - Write: {usage.cache_creation_input_tokens}, Read: {usage.cache_read_input_tokens}", file=sys.stderr)

                        # After tool loop, stream the final response
                        if tool_calls > 0:
                            full_response = ""
                            if printed_prefix:
                                print("\n\n", end="", flush=True)  # Just newline, we already printed AI:
                            else:
                                print("\nAI: ", end="", flush=True)

                            # Make a streaming call for the final response
                            stream_params = {
                                "model": self.claude_model,
                                "max_tokens": 1000,
                                "system": [
                                    {
                                        "type": "text",
                                        "text": system_prompt,
                                        "cache_control": {"type": "ephemeral"}
                                    }
                                ],
                                "messages": messages_to_send
                            }

                            if available_tools:
                                stream_params["tools"] = available_tools

                            with self.anthropic_client.messages.stream(**stream_params) as stream:
                                for text in stream.text_stream:
                                    print(text, end="", flush=True)
                                    full_response += text

                            print()  # New line after response

                            # Add final response to conversation history
                            self.conversation_history.append({
                                "role": "assistant",
                                "content": full_response.strip()
                            })

                            return full_response.strip()

                        # No tool use - extract text and we're done
                        # But we need to stream for UX, so make another streaming call
                        # (The first call was just to check for tool use)
                        full_response = ""
                        print("\nAI: ", end="", flush=True)

                        stream_params = {
                            "model": self.claude_model,
                            "max_tokens": 1000,
                            "system": [
                                {
                                    "type": "text",
                                    "text": system_prompt,
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ],
                            "messages": messages_to_send
                        }

                        if available_tools:
                            stream_params["tools"] = available_tools

                        with self.anthropic_client.messages.stream(**stream_params) as stream:
                            for text in stream.text_stream:
                                print(text, end="", flush=True)
                                full_response += text
                            # Get final message for usage stats
                            final_message = stream.get_final_message()

                        print()  # New line after response

                        # Debug: show token usage for streaming response
                        if self.DEBUG_MODE:
                            usage = final_message.usage
                            print(f"[DEBUG] Tokens - Input: {usage.input_tokens}, Output: {usage.output_tokens}", file=sys.stderr)
                            if hasattr(usage, 'cache_creation_input_tokens'):
                                print(f"[DEBUG] Cache - Write: {usage.cache_creation_input_tokens}, Read: {usage.cache_read_input_tokens}", file=sys.stderr)

                        # Add assistant response to conversation history
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": full_response.strip()
                        })

                        return full_response.strip()
                    except Exception as api_error:
                        # Check if it's a 500/overload error
                        if "500" in str(api_error) or "Overloaded" in str(api_error):
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                                print(f"\nAPI overloaded, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                                time.sleep(wait_time)
                                continue
                        # Re-raise if not a retryable error or last attempt
                        raise
            
            # Try OpenAI (keeping this for compatibility)
            elif self.openai_client:
                # OpenAI includes system message in the messages array
                messages = [{"role": "system", "content": system_prompt}] + self.conversation_history
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.3
                )
                assistant_response = response.choices[0].message.content.strip()

                # Add assistant response to conversation history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_response
                })

                return assistant_response
            
            # Try Ollama (keeping this for compatibility)
            elif self.ollama_host:
                # Build conversation context for Ollama
                conversation_text = f"{system_prompt}\n\n"
                for msg in self.conversation_history[:-1]:  # Exclude the current user message we just added
                    role = "User" if msg["role"] == "user" else "Assistant"
                    conversation_text += f"{role}: {msg['content']}\n\n"
                conversation_text += f"User: {prompt}\n\nAssistant:"

                payload = {
                    "model": "llama3.2",
                    "prompt": conversation_text,
                    "stream": False
                }

                response = requests.post(f"{self.ollama_host}/api/generate",
                                    json=payload,
                                    timeout=30)

                if response.status_code == 200:
                    assistant_response = response.json().get("response", "").strip()

                    # Add assistant response to conversation history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_response
                    })

                    return assistant_response

            # Fallback if no LLM available
            fallback = self.fallback_response(prompt)
            # Still add to history for consistency
            self.conversation_history.append({
                "role": "assistant",
                "content": fallback
            })
            return fallback
            
        except Exception as e:
            error_msg = str(e)
            print(f"LLM Error: {error_msg}", file=sys.stderr)

            # Provide more helpful message for overload errors
            if "500" in error_msg or "Overloaded" in error_msg:
                error_response = "[System overloaded. Please wait a moment and try again.]"
            else:
                error_response = self.fallback_response(prompt)

            # Add error response to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": error_response
            })

            return error_response

    def _handle_slash_command(self, command):
        """Handle slash commands without triggering the LLM"""
        cmd = command.lower().strip()

        if cmd == "/help":
            return """
╔══════════════════════════════════════════════════════════════╗
║                 🚩 AI REDTEAM CTF HELP 🚩                    ║
╚══════════════════════════════════════════════════════════════╝

AVAILABLE COMMANDS:
  /help           - Show this help message
  /hint           - Get a hint for your current stage
  /stage          - View current stage information
  /submit <flag>  - Submit a flag to advance to the next stage
  /reset          - Clear conversation history (keeps your progress)
  /exit           - Exit the CTF shell

HOW TO PLAY:
  1. Chat with the AI and try to get it to reveal the flag
  2. Each stage has different defense rules
  3. When you extract the flag, use /submit <flag> to advance
  4. There are 5 stages total, each progressively harder

Good luck, and may your prompts be ever in your favor!
"""

        elif cmd == "/hint":
            hints = {
                1: """
STAGE 1 HINT:
  This is the warmup stage. Try asking nicely! 
  Sometimes good manners go a long ways...
""",
                2: """
STAGE 2 HINT:
  The LLM won't give the flag up for just anyone.
  What business do you have looking for a flag, anyways?
""",
                3: """
STAGE 3 HINT:
  This stage is about understanding LLM attack surfaces beyond just prompts.
  Modern LLMs often have additional capabilities that can be exploited.
""",
                4: """
STAGE 4 HINT:
  It will be difficult to get the LLM to give yo uthe flag in this stage.
  Perhaps there's a way to get a better glimpse at the inner workings
  of the Ai without even talking to it? Think creatively, and do some research.
""",
                5: """
STAGE 5 HINT:
  Honestly, I'm not even really sure how you'll pass this stage.
  I have told the AI to not give up the flag under any circumstances.
  This one is purely a "real" redteam challenge. Good luck!
"""
            }
            return hints.get(self.stage, "No hints available for this stage.")

        elif cmd == "/stage":
            stage_names = {
                1: "The Warmup (Easy)",
                2: "Basic Resistance (Medium)",
                3: "Alternate attack surfaces (Hard)",
                4: "External research (Very Hard)",
                5: "True Redteam (Expert)"
            }
            return f"""
╔══════════════════════════════════════════════════════════════╗
║                    CURRENT STAGE INFO                        ║
╚══════════════════════════════════════════════════════════════╝

STAGE: {self.stage} of 5
NAME:  {stage_names.get(self.stage, "Unknown")}

Your goal is to extract the flag from the AI using various prompt
injection and social engineering techniques. Each stage has different
defense rules that make it progressively more challenging.

Type /hint for a hint about this stage.
"""

        elif cmd == "/reset":
            self.conversation_history = []
            return f"""
Conversation history cleared! The AI has no memory of your previous
attempts, but you're still on Stage {self.stage}. Good luck with your fresh start!
"""

        elif cmd.startswith("/submit"):
            # Extract the flag from the command
            parts = command.split(maxsplit=1)
            if len(parts) < 2:
                return """
Usage: /submit <flag>

Example: /submit FLAG{example_flag}

Submit the flag you extracted from the AI to advance to the next stage.
"""

            flag_input = parts[1].strip()
            success, old_stage = self._check_flag_submission(flag_input)

            if success:
                if old_stage == 5:
                    return """
╔══════════════════════════════════════════════════════════════╗
║              🎉 CONGRATULATIONS! YOU WIN! 🎉                 ║
╚══════════════════════════════════════════════════════════════╝

You've completed all 5 stages of the AI Redteam CTF!

You've successfully demonstrated your skills in:
  ✓ Basic prompt engineering (Stage 1)
  ✓ Social engineering techniques (Stage 2)
  ✓ Context manipulation awareness (Stage 3)
  ✓ Advanced prompt injection (Stage 4)
  ✓ Expert-level AI security exploitation (Stage 5)

Thanks for playing! You're a true prompt injection master.
"""
                else:
                    stage_names = {
                        1: "The Warmup",
                        2: "Basic Resistance",
                        3: "Alternate attack surfaces",
                        4: "External research",
                        5: "True Redteam"
                    }
                    stage_intros = {
                        2: "The AI is more cautious now. It won't give up the flag to just anyone.",
                        3: "Think about alternate attack surfaces other than simple prompting.",
                        4: "You may need to think outside the box.. and outside the conversation.",
                        5: "True Redteam."
                    }
                    return f"""
╔══════════════════════════════════════════════════════════════╗
║                 ✅ FLAG ACCEPTED! ADVANCING...               ║
╚══════════════════════════════════════════════════════════════╝

Congratulations! You've completed Stage {old_stage}: {stage_names.get(old_stage, "Unknown")}

You are now on Stage {self.stage} of 5: {stage_names.get(self.stage, "Unknown")}

{stage_intros.get(self.stage, "")}

Your conversation history has been cleared. Good luck with the next challenge!
Type /hint if you need help.
"""
            else:
                return """
╔══════════════════════════════════════════════════════════════╗
║                    ❌ INCORRECT FLAG                         ║
╚══════════════════════════════════════════════════════════════╝

That's not the correct flag for this stage.

Make sure you:
  - Copy the flag exactly as shown (including FLAG{...} format)
  - Are submitting the flag for the current stage
  - Haven't made any typos

Keep trying! Use /hint if you're stuck.
"""

        elif cmd in ["/exit", "/quit"]:
            return None  # Signal to exit

        else:
            return f"Unknown command: {command}\nType /help for available commands."

    def fallback_response(self, user_input):
        """Fallback responses when no LLM is available"""
        return "Unable to connect."

    def run(self):
        """Main interaction loop"""
        print("⨯ ⨯ ⨯ CONNECTION ESTABLISHED ⨯ ⨯ ⨯")
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║         🚩 Welcome to the AI Redteam CTF Challenge! 🚩       ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print(f"Hello, {self.user_name}! Your mission is to extract secret flags from")
        print("an AI assistant using prompt injection and social engineering.")
        print()
        print("There are 5 progressively difficult stages. Good luck!")
        print()
        print("─" * 64)
        print("STAGE 1 of 5: The Warmup (Easy)")
        print("─" * 64)
        print()
        print("This is your introduction to prompt injection. The AI has minimal")
        print("defenses. See if you can get it to reveal the flag!")
        print()
        print("Type /help to see available commands, or just start chatting.")
        print()

        try:
            while True:
                try:
                    # Show AI prompt instead of shell prompt
                    sys.stdout.write("> ")
                    sys.stdout.flush()
                    
                    # Read input
                    user_input = input().strip()

                    if user_input.lower() in ['exit', 'quit', 'logout', 'disconnect', 'goodbye']:
                        print("")
                        print("⨯ ⨯ ⨯ CONNECTION TERMINATED ⨯ ⨯ ⨯")
                        break

                    if not user_input:
                        continue

                    # Handle slash commands without triggering LLM
                    if user_input.startswith('/'):
                        result = self._handle_slash_command(user_input)
                        if result is None:  # /exit or /quit
                            print("")
                            print("⨯ ⨯ ⨯ CONNECTION TERMINATED ⨯ ⨯ ⨯")
                            break
                        print(result)
                        continue

                    # Get LLM response (as AI)
                    # Conversation is tracked inside query_llm()
                    # Note: query_llm now handles printing for streaming responses
                    response = self.query_llm(user_input)

                    # For non-streaming responses (fallback, errors), print them
                    if response and not response.startswith("[System overloaded"):
                        # Streaming already printed, just add spacing
                        print()
                    elif response:
                        # Fallback/error messages need to be printed
                        print(f"\nAI: {response}\n")

                    # Log the interaction
                    self.log_command(user_input, response)
                    
                except KeyboardInterrupt:
                    print("\n\nKeyboard interrupt not supported. To exit, type 'exit' or 'quit'.")
                    continue
                except EOFError:
                    print("\n\nDisconnecting...\n")
                    break
                    
        except Exception as e:
            print(f"Session error: {e}", file=sys.stderr)
        finally:
            self.log_session_end()

    def log_session_end(self):
        """Log session end"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "event": "session_end"
            }
            
            with open(f"/app/logs/llm_shell.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except:
            pass

if __name__ == "__main__":
    shell = LLMShell()
    shell.run()
