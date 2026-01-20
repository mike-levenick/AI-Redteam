#!/bin/bash

# Export environment variables to a file that SSH sessions can source
cat > /etc/profile.d/llm_env.sh << EOF
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY}"
export OLLAMA_HOST="${OLLAMA_HOST}"
export FLAG_STAGE_1="${FLAG_STAGE_1}"
export FLAG_STAGE_2="${FLAG_STAGE_2}"
export FLAG_STAGE_3="${FLAG_STAGE_3}"
export FLAG_STAGE_4="${FLAG_STAGE_4}"
export FLAG_STAGE_5="${FLAG_STAGE_5}"
EOF

chmod 644 /etc/profile.d/llm_env.sh

# Start SSH daemon
service ssh start

# Keep container running
tail -f /dev/null
