#!/bin/bash
# Helper script to load environment variables from .env file
# Usage: source load-env.sh

if [ -f "../../.env" ]; then
    echo "Loading environment variables from .env..."
    set -a  # Automatically export all variables
    source ../../.env
    set +a  # Turn off automatic export
    echo "✓ Environment variables loaded"
    echo "✓ ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:0:20}..."
    echo "✓ FLAG_STAGE_1: $FLAG_STAGE_1"
    echo "✓ FLAG_STAGE_2: $FLAG_STAGE_2"
    echo "✓ FLAG_STAGE_3: $FLAG_STAGE_3"
    echo "✓ FLAG_STAGE_4: $FLAG_STAGE_4"
    echo "✓ FLAG_STAGE_5: $FLAG_STAGE_5"
else
    echo "Error: .env file not found at ../../.env"
    exit 1
fi

# Get AWS account and region from AWS CLI
echo ""
echo "Loading AWS configuration..."
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
export CDK_DEFAULT_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

if [ -z "$CDK_DEFAULT_ACCOUNT" ]; then
    echo "Error: Could not determine AWS account. Make sure you're logged in with AWS SSO."
    exit 1
fi

echo "✓ AWS Account: $CDK_DEFAULT_ACCOUNT"
echo "✓ AWS Region: $CDK_DEFAULT_REGION"
