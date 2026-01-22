"""
AWS CDK Stack for AI Redteam CTF
"""
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct
import os


class AIRedteamCTFStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda Function
        ctf_function = lambda_.Function(
            self,
            "CTFFunction",
            function_name="ai-redteam-ctf-web",
            description="AI Redteam CTF web backend",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="lambda_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../../lambda"),
                bundling={
                    "image": lambda_.Runtime.PYTHON_3_11.bundling_image,
                    "command": [
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp -r . /asset-output"
                    ]
                }
            ),
            memory_size=512,
            timeout=Duration.minutes(15),  # Max Lambda timeout
            environment={
                'ANTHROPIC_API_KEY': config['anthropic_api_key'],
                'FLAG_STAGE_1': config['flag_stage_1'],
                'FLAG_STAGE_2': config['flag_stage_2'],
                'FLAG_STAGE_3': config['flag_stage_3'],
                'FLAG_STAGE_4': config['flag_stage_4'],
                'FLAG_STAGE_5': config['flag_stage_5'],
            }
        )

        # Lambda Function URL with Response Streaming
        function_url = ctf_function.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=["*"],
                allowed_methods=[lambda_.HttpMethod.GET, lambda_.HttpMethod.POST, lambda_.HttpMethod.OPTIONS],
                allowed_headers=["*"],
                max_age=Duration.minutes(5)
            ),
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM  # Required for SSE
        )

        # S3 Bucket for Frontend
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            website_index_document="index.html",
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            auto_delete_objects=True,  # Clean up on stack deletion
            removal_policy=RemovalPolicy.DESTROY  # Allow bucket deletion
        )

        # Deploy Frontend Files to S3
        s3_deploy.BucketDeployment(
            self,
            "DeployFrontend",
            sources=[
                s3_deploy.Source.asset(
                    os.path.join(os.path.dirname(__file__), "../../frontend")
                )
            ],
            destination_bucket=frontend_bucket,
        )

        # CloudFront Distribution (Optional but recommended for production)
        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            comment="AI Redteam CTF Frontend"
        )

        # Outputs
        CfnOutput(
            self,
            "LambdaFunctionUrl",
            value=function_url.url,
            description="Lambda Function URL for API backend",
            export_name=f"{self.stack_name}-ApiUrl"
        )

        CfnOutput(
            self,
            "FrontendBucketUrl",
            value=frontend_bucket.bucket_website_url,
            description="S3 Website URL",
            export_name=f"{self.stack_name}-FrontendUrl"
        )

        CfnOutput(
            self,
            "CloudFrontUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="CloudFront Distribution URL (Recommended)",
            export_name=f"{self.stack_name}-CloudFrontUrl"
        )

        CfnOutput(
            self,
            "FunctionName",
            value=ctf_function.function_name,
            description="Lambda Function Name",
            export_name=f"{self.stack_name}-FunctionName"
        )

        # Output instruction for updating frontend
        CfnOutput(
            self,
            "NextSteps",
            value=f"Update frontend/app.js: const API_BASE_URL = '{function_url.url.rstrip('/')}'",
            description="Action Required"
        )
