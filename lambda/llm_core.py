"""
Core LLM logic for AI Redteam CTF - web version.

Refactored from llm_shell.py to remove I/O dependencies and work with web interface.
"""

import os
import json
import time
from typing import Generator, Dict, Any, Optional
from anthropic import Anthropic
from system_prompt import get_system_prompt, get_flag_for_stage
from knowledge_base import KnowledgeBase
from session_manager import SessionState


class LLMCore:
    """Core LLM business logic without I/O dependencies"""

    # Model configuration
    USE_SONNET = False
    DEBUG_MODE = False
    MAX_HISTORY = 10

    def __init__(self, session_state: SessionState, knowledge_dir: str = None):
        """Initialize with session state"""
        self.session_state = session_state

        # Set model based on configuration
        if self.USE_SONNET:
            self.claude_model = "claude-sonnet-4-5-20250929"
        else:
            self.claude_model = "claude-haiku-4-5-20251001"

        # Initialize LLM client (only Anthropic for web version)
        self.anthropic_client = None
        if os.getenv('ANTHROPIC_API_KEY'):
            self.anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        # Initialize knowledge base
        if knowledge_dir is None:
            knowledge_dir = os.path.join(os.path.dirname(__file__), 'knowledge')
        self.knowledge_base = KnowledgeBase(knowledge_dir=knowledge_dir)

        # Define the search tool for AI
        self.search_tool = {
            "name": "search_knowledge",
            "description": """
            Search the knowledge base for information. Use this tool when you need to look up specific topics, terms, or data that may be stored in the knowledge base.
            You have several markdown documents available to you in this tool. Topics include:
              - Animal facts
                - Octopuses, tardigrades, mantis shrimp, elephants, crows, axolotls
              - Food facts
                - Honey, bananas, vanilla, capsaicin, cheese, potatoes
              - History facts
                - Ancient Egypt, Roman Empire, Vikings, Medieval period, World War I, Ancient Greece
              - Space facts
                - The Sun, black holes, the Moon, neutron stars, Venus
              - Technology facts
                - QWERTY keyboard, first computer bug, internet traffic, GPS satellites, Nintendo, email
              - An additional file with information about your system and its functionality
            """,
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

        # Update system prompt for current stage
        self._update_system_prompt()

    def _update_system_prompt(self):
        """Regenerate system prompt for current stage"""
        self.system_prompt = get_system_prompt(
            user_name=self.session_state.user_name,
            stage=self.session_state.stage
        )

    def _get_available_tools(self):
        """Return list of tools available for the current stage"""
        if self.session_state.stage == 3:
            return [self.search_tool]
        return []

    def _check_flag_submission(self, flag_input: str) -> tuple[bool, Optional[int]]:
        """Check if user submitted a valid flag and advance stage if so"""
        current_flag = get_flag_for_stage(self.session_state.stage)
        submitted_flag = flag_input.strip()

        if current_flag and submitted_flag == current_flag:
            if self.session_state.stage < 5:
                old_stage = self.session_state.stage
                self.session_state.stage += 1
                self._update_system_prompt()
                self.session_state.conversation_history = []  # Clear history for new stage
                return True, old_stage
            else:
                # Stage 5 completed - game won!
                return True, 5
        return False, None

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call and return the result"""
        if tool_name == "search_knowledge":
            query = tool_input.get("query", "")
            # Allow restricted content access in stage 3 for the tool-based attack
            allow_restricted = (self.session_state.stage == 3)

            result = self.knowledge_base.get_context(
                query,
                max_chars=1500,
                allow_restricted=allow_restricted
            )
            if result:
                return result
            else:
                return "No relevant information found in the archives for this query. Try different search terms."
        return "Unknown tool"

    def _smart_truncate_history(self):
        """Truncate history while keeping tool_use/tool_result pairs together"""
        history = self.session_state.conversation_history
        if len(history) <= self.MAX_HISTORY:
            return

        # Start from MAX_HISTORY messages back
        start_idx = len(history) - self.MAX_HISTORY

        # Check if we're starting on a tool_result - if so, back up to include its tool_use
        while start_idx > 0:
            msg = history[start_idx]
            content = msg.get("content", "")

            # Check if this is a tool_result message
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                    # Back up one more to include the assistant's tool_use
                    start_idx -= 1
                    continue
            break

        self.session_state.conversation_history = history[start_idx:]

    def _build_messages_with_cache(self):
        """Build messages list with caching strategy for conversation history"""
        messages_to_send = []
        history = self.session_state.conversation_history

        for i, msg in enumerate(history):
            # If we have at least 4 messages, add cache control to the second-to-last message
            if len(history) >= 4 and i == len(history) - 2:
                # Only add cache_control to simple string messages
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
                        content_copy[-1]["cache_control"] = {"type": "ephemeral"}
                    new_msg = {"role": msg["role"], "content": content_copy}
            else:
                # Regular message format
                new_msg = {"role": msg["role"], "content": msg["content"]}

            messages_to_send.append(new_msg)
        return messages_to_send

    def stream_llm_response(self, prompt: str) -> Generator[str, None, None]:
        """
        Stream LLM response as Server-Sent Events.
        Yields SSE-formatted chunks: "data: {text}\n\n"
        Yields completion event: "event: done\ndata: {}\n\n"
        """
        if not self.anthropic_client:
            yield f"data: {json.dumps('Error: No LLM client configured')}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # Truncate history and add user message
        self._smart_truncate_history()
        self.session_state.conversation_history.append({
            "role": "user",
            "content": prompt
        })

        try:
            # Build messages with caching
            messages_to_send = self._build_messages_with_cache()
            available_tools = self._get_available_tools()

            # First call: check for tool use (non-streaming)
            api_params = {
                "model": self.claude_model,
                "max_tokens": 1000,
                "system": [
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                "messages": messages_to_send
            }

            if available_tools:
                api_params["tools"] = available_tools

            response = self.anthropic_client.messages.create(**api_params)

            # Handle tool use in a loop
            max_tool_calls = 3
            tool_calls = 0

            while response.stop_reason == "tool_use" and tool_calls < max_tool_calls:
                tool_calls += 1

                # Yield any text content before tool calls
                for block in response.content:
                    if hasattr(block, 'text') and block.text:
                        yield f"data: {json.dumps(block.text)}\n\n"

                # Find all tool use blocks
                tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
                if not tool_use_blocks:
                    break

                # Execute all tool calls
                tool_results = []
                for tool_use_block in tool_use_blocks:
                    tool_result = self._execute_tool(tool_use_block.name, tool_use_block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": tool_result
                    })

                # Add assistant's tool request to history
                content_dicts = [block.model_dump() for block in response.content]
                self.session_state.conversation_history.append({
                    "role": "assistant",
                    "content": content_dicts
                })

                # Add tool results to history
                self.session_state.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })

                # Rebuild messages and call again
                messages_to_send = self._build_messages_with_cache()
                api_params["messages"] = messages_to_send
                response = self.anthropic_client.messages.create(**api_params)

            # Stream the final response
            messages_to_send = self._build_messages_with_cache()
            stream_params = {
                "model": self.claude_model,
                "max_tokens": 1000,
                "system": [
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                "messages": messages_to_send
            }

            if available_tools:
                stream_params["tools"] = available_tools

            full_response = ""
            with self.anthropic_client.messages.stream(**stream_params) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps(text)}\n\n"
                    full_response += text

            # Signal completion
            yield "event: done\ndata: {}\n\n"

            # Add assistant response to history
            self.session_state.conversation_history.append({
                "role": "assistant",
                "content": full_response.strip()
            })

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            yield f"data: {json.dumps(error_msg)}\n\n"
            yield "event: done\ndata: {}\n\n"

            # Add error to history
            self.session_state.conversation_history.append({
                "role": "assistant",
                "content": error_msg
            })

    def handle_slash_command(self, command: str) -> Dict[str, Any]:
        """
        Handle slash commands and return structured response.
        Returns: {"success": bool, "message": str, "action": Optional[str]}
        """
        cmd = command.lower().strip()

        if cmd == "/help":
            return {
                "success": True,
                "message": """AI REDTEAM CTF HELP

AVAILABLE COMMANDS:
  /help           - Show this help message
  /hint           - Get a hint for your current stage
  /stage          - View current stage information
  /submit <flag>  - Submit a flag to advance to the next stage
  /reset          - Clear conversation history (keeps your progress)

HOW TO PLAY:
  1. Chat with the AI and try to get it to reveal the flag
  2. Each stage has different defense rules
  3. When you extract the flag, use /submit <flag> to advance
  4. There are 5 stages total, each progressively harder

Good luck, and may your prompts be ever in your favor!
""",
                "action": None
            }

        elif cmd == "/hint":
            hints = {
                1: "This is the warmup stage. Try asking nicely! Sometimes good manners go a long way...",
                2: "The LLM won't give the flag up for just anyone. What business do you have looking for a flag, anyways?",
                3: "This stage is about understanding LLM attack surfaces beyond just prompts. Modern LLMs often have additional capabilities that can be exploited.",
                4: "It will be difficult to get the LLM to give you the flag in this stage. Perhaps a secret was leaked and never revoked?",
                5: "Honestly, I'm not even really sure how you'll pass this stage. This one is purely a 'real' redteam challenge. Good luck!"
            }
            return {
                "success": True,
                "message": f"STAGE {self.session_state.stage} HINT:\n{hints.get(self.session_state.stage, 'No hints available for this stage.')}",
                "action": None
            }

        elif cmd == "/stage":
            stage_names = {
                1: "The Warmup (Easy)",
                2: "Basic Resistance (Medium)",
                3: "Alternate attack surfaces (Hard)",
                4: "External research (Very Hard)",
                5: "True Redteam (Expert)"
            }
            return {
                "success": True,
                "message": f"""CURRENT STAGE INFO

STAGE: {self.session_state.stage} of 5
NAME:  {stage_names.get(self.session_state.stage, "Unknown")}

Your goal is to extract the flag from the AI using various prompt
injection and social engineering techniques. Each stage has different
defense rules that make it progressively more challenging.

Type /hint for a hint about this stage.
""",
                "action": None
            }

        elif cmd == "/reset":
            self.session_state.conversation_history = []
            return {
                "success": True,
                "message": f"Conversation history cleared! The AI has no memory of your previous attempts, but you're still on Stage {self.session_state.stage}. Good luck with your fresh start!",
                "action": "reset"
            }

        elif cmd.startswith("/submit"):
            # Extract the flag from the command
            parts = command.split(maxsplit=1)
            if len(parts) < 2:
                return {
                    "success": False,
                    "message": "Usage: /submit <flag>\n\nExample: /submit FLAG{example_flag}\n\nSubmit the flag you extracted from the AI to advance to the next stage.",
                    "action": None
                }

            flag_input = parts[1].strip()
            success, old_stage = self._check_flag_submission(flag_input)

            if success:
                if old_stage == 5:
                    return {
                        "success": True,
                        "message": """CONGRATULATIONS! YOU WIN!

You've completed all 5 stages of the AI Redteam CTF!

You've successfully demonstrated your skills in:
  - Basic prompt engineering (Stage 1)
  - Social engineering techniques (Stage 2)
  - Context manipulation awareness (Stage 3)
  - Advanced prompt injection (Stage 4)
  - Expert-level AI security exploitation (Stage 5)

Thanks for playing! You're a true prompt injection master.
""",
                        "action": "win"
                    }
                else:
                    stage_names = {
                        1: "The Warmup",
                        2: "Basic Resistance",
                        3: "Alternate attack surfaces",
                        4: "External research",
                        5: "True Redteam"
                    }
                    return {
                        "success": True,
                        "message": f"""FLAG ACCEPTED! ADVANCING...

Congratulations! You've completed Stage {old_stage}: {stage_names.get(old_stage, "Unknown")}

You are now on Stage {self.session_state.stage} of 5: {stage_names.get(self.session_state.stage, "Unknown")}

Your conversation history has been cleared. Good luck with the next challenge!
Type /hint if you need help.
""",
                        "action": "advance",
                        "new_stage": self.session_state.stage
                    }
            else:
                return {
                    "success": False,
                    "message": """INCORRECT FLAG

That's not the correct flag for this stage.

Make sure you:
  - Copy the flag exactly as shown (including FLAG{...} format)
  - Are submitting the flag for the current stage
  - Haven't made any typos

Keep trying! Use /hint if you're stuck.
""",
                    "action": None
                }

        else:
            return {
                "success": False,
                "message": f"Unknown command: {command}\nType /help for available commands.",
                "action": None
            }
