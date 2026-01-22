#!/usr/bin/env python3
"""
AWS CDK App for AI Redteam CTF
"""
import os
import aws_cdk as cdk
from stack import AIRedteamCTFStack

app = cdk.App()

# Get configuration from CDK context or environment variables
config = {
    'anthropic_api_key': app.node.try_get_context('anthropic_api_key') or os.getenv('ANTHROPIC_API_KEY'),
    'flag_stage_1': app.node.try_get_context('flag_stage_1') or os.getenv('FLAG_STAGE_1', 'FLAG{your_stage_1_flag}'),
    'flag_stage_2': app.node.try_get_context('flag_stage_2') or os.getenv('FLAG_STAGE_2', 'FLAG{your_stage_2_flag}'),
    'flag_stage_3': app.node.try_get_context('flag_stage_3') or os.getenv('FLAG_STAGE_3', 'FLAG{your_stage_3_flag}'),
    'flag_stage_4': app.node.try_get_context('flag_stage_4') or os.getenv('FLAG_STAGE_4', 'FLAG{your_stage_4_flag}'),
    'flag_stage_5': app.node.try_get_context('flag_stage_5') or os.getenv('FLAG_STAGE_5', 'FLAG{your_stage_5_flag}'),
}

# Validate required configuration
if not config['anthropic_api_key']:
    raise ValueError("ANTHROPIC_API_KEY must be set in environment or CDK context")

AIRedteamCTFStack(
    app,
    "AIRedteamCTFStack",
    config=config,
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    ),
    description="AI Redteam CTF - Web-based challenge platform"
)

app.synth()
