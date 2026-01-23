# AWS CDK Deployment for AI Redteam CTF

This directory contains AWS CDK infrastructure code to deploy the AI Redteam CTF to AWS.

## What Gets Deployed

1. **Lambda Function**: Handles API requests with response streaming for SSE
2. **Lambda Function URL**: Public HTTPS endpoint with CORS enabled
3. **S3 Bucket**: Hosts the frontend static files with website hosting
4. **CloudFront Distribution**: CDN for the frontend (recommended for production)

## Prerequisites

### 1. Install AWS CDK CLI

```bash
npm install -g aws-cdk
```

### 2. Install Python Dependencies

```bash
cd infrastructure/cdk
pip install -r requirements.txt
```

### 3. Configure AWS Credentials

```bash
aws configure
```

Enter your AWS Access Key ID, Secret Access Key, and default region.

### 4. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

Replace `ACCOUNT-ID` with your AWS account ID and `REGION` with your target region (e.g., `us-east-1`).

## Deployment Steps

### Step 1: Set Environment Variables

```bash
cd infrastructure/cdk

# Load environment variables from root .env file
source load-env.sh
```

This will load your API key and flags from the `.env` file in the project root.

### Step 2: Bundle Lambda Code (No Docker Required)

```bash
# Bundle Lambda code with dependencies
./bundle-lambda.sh
```

This creates `lambda-bundle/` with all Python code and dependencies packaged together. No Docker needed!

### Step 3: Synthesize CloudFormation Template (Optional)

Preview what will be deployed:

```bash
cdk synth
```

This generates CloudFormation templates in `cdk.out/`.

### Step 4: Deploy

```bash
cdk deploy
```

You'll see a preview of changes and be prompted to confirm. Type `y` to proceed.

The deployment will:
- Create Lambda function
- Set up Function URL with CORS
- Create S3 bucket
- Upload frontend files
- Create CloudFront distribution
- Output all URLs

### Step 5: Update Frontend Configuration

After deployment completes, you'll see outputs like:

```
Outputs:
AIRedteamCTFStack.LambdaFunctionUrl = https://abc123xyz.lambda-url.us-east-1.on.aws/
AIRedteamCTFStack.CloudFrontUrl = https://d111111abcdef8.cloudfront.net
AIRedteamCTFStack.NextSteps = Update frontend/app.js: const API_BASE_URL = 'https://...'
```

**IMPORTANT**: You need to update the frontend with the Lambda Function URL:

```bash
# Back to project root
cd ../..

# Edit frontend/app.js
# Change line 7 from:
# const API_BASE_URL = 'http://localhost:5001';
# To:
# const API_BASE_URL = 'https://abc123xyz.lambda-url.us-east-1.on.aws';
```

### Step 6: Redeploy Frontend with Updated API URL

```bash
cd infrastructure/cdk
cdk deploy
```

This will upload the updated frontend files with the correct API endpoint.

### Step 7: Access Your CTF

Open the CloudFront URL in your browser:
```
https://d111111abcdef8.cloudfront.net
```

Or use the S3 website URL (HTTP only):
```
http://your-bucket-name.s3-website-us-east-1.amazonaws.com
```

## Managing Your Deployment

### View Stack Status

```bash
cdk ls
```

### View Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name AIRedteamCTFStack \
  --query 'Stacks[0].Outputs'
```

### Update Deployment

After making changes to Lambda code or frontend:

```bash
cdk deploy
```

### View Lambda Logs

```bash
aws logs tail /aws/lambda/ai-redteam-ctf-web --follow
```

### Destroy Everything

```bash
cdk destroy
```

This will delete all resources created by the stack.

## Configuration Options

### Using CDK Context Instead of Environment Variables

You can pass configuration via CDK context:

```bash
cdk deploy \
  -c anthropic_api_key="your_key" \
  -c flag_stage_1="FLAG{...}" \
  -c flag_stage_2="FLAG{...}" \
  -c flag_stage_3="FLAG{...}" \
  -c flag_stage_4="FLAG{...}" \
  -c flag_stage_5="FLAG{...}"
```

### Changing AWS Region

```bash
export CDK_DEFAULT_REGION=us-west-2
cdk deploy
```

## Troubleshooting

### "Failed to connect to docker API"

This deployment **does not require Docker**. If you see Docker errors:

1. Make sure you ran `./bundle-lambda.sh` first
2. The script bundles dependencies locally without Docker
3. If you still see Docker errors, check that `lambda-bundle/` directory exists

### Lambda Deployment Package Too Large

If you get errors about package size, the `anthropic` package might be too large. Consider:
- Using a Lambda Layer for dependencies
- Removing unused dependencies

### Function URL Not Working

Check CORS configuration in CloudWatch Logs:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/ai-redteam-ctf-web \
  --filter-pattern "CORS"
```

### Frontend Shows "Failed to create session"

1. Check the API URL in `frontend/app.js` matches the Lambda Function URL output
2. Check browser console for CORS errors
3. Verify Lambda is responding:
   ```bash
   curl https://your-function-url.lambda-url.us-east-1.on.aws/health
   ```

### CloudFront Takes Time to Deploy

CloudFront distributions can take 15-20 minutes to fully deploy. You can use the S3 website URL immediately while CloudFront propagates.

## Cost Estimate

- **Lambda**: ~$5/month for moderate usage
- **S3**: ~$1/month for storage and requests
- **CloudFront**: Free tier covers 1TB/month, then ~$0.085/GB
- **Claude API**: ~$10-20/month (Haiku 4.5)

**Estimated Total**: $15-30/month for moderate usage

## Architecture Diagram

```
User Browser
    |
    v
CloudFront (HTTPS)
    |
    v
S3 Static Website (HTML/JS/CSS)
    |
    v (API Calls)
Lambda Function URL (SSE Streaming)
    |
    v
Anthropic Claude API
```

## Differences from SAM

| Feature | SAM | CDK |
|---------|-----|-----|
| Language | YAML | Python/TypeScript/etc |
| Frontend Deployment | Manual | Automatic via BucketDeployment |
| CloudFront | Manual | Included in stack |
| Type Safety | No | Yes (with IDE support) |
| Reusability | Limited | High (constructs) |

## Next Steps

1. Set up CloudWatch alarms for Lambda errors
2. Enable AWS WAF for CloudFront (DDoS protection)
3. Add custom domain name with Route53
4. Set up DynamoDB for persistent sessions (optional)
5. Add API Gateway for rate limiting (optional)

## Support

For CDK-specific issues:
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [CDK Python Examples](https://github.com/aws-samples/aws-cdk-examples/tree/master/python)

For CTF issues, check [README-WEB.md](../../README-WEB.md)
