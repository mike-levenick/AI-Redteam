#!/bin/bash

echo "🤖 Setting up LLM Shell..."

# Create logs directory
mkdir -p logs

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Created .env file. Configure your LLM provider:"
    echo "   - For Claude: Add ANTHROPIC_API_KEY"
    echo "   - For OpenAI: Add OPENAI_API_KEY" 
    echo "   - For Ollama: Add OLLAMA_HOST (e.g., http://host.docker.internal:11434)"
    echo ""
fi

# Build and start
echo "🐳 Building Docker container..."
docker-compose build

echo "🚀 Starting LLM shell..."
docker-compose up -d

echo ""
echo "✅ LLM Shell is ready!"
echo ""
echo "🔗 Connect via SSH:"
echo "   ssh llmuser@localhost"
echo "   Password: password"
echo ""
echo "📋 View logs:"
echo "   docker-compose logs -f"
echo "   tail -f logs/llm_shell.jsonl"
echo ""
echo "🛑 To stop:"
echo "   docker-compose down"
echo ""

# Check status
sleep 2
docker-compose ps
