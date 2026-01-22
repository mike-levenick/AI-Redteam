# AI Redteam CTF - Web Version

This is the web-based version of the AI Redteam CTF, converted from SSH to a browser-based chat interface.

## Architecture

- **Backend**: AWS Lambda with Function URLs (or local Flask for development)
- **Frontend**: Single-page application (vanilla HTML/JS)
- **Streaming**: Server-Sent Events (SSE) for real-time AI responses
- **Sessions**: In-memory (anonymous, no login required)
- **Deployment**: AWS Lambda + S3/CloudFront

## Quick Start - Local Development

### 1. Install Dependencies

```bash
# Install Python dependencies for development server
cd scripts
pip install -r requirements-dev.txt
cd ..
```

### 2. Configure Environment Variables

Create a `.env` file in the root directory:

```bash
# Anthropic API key (required)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Flags for each stage
FLAG_STAGE_1=FLAG{please_is_the_magic_word}
FLAG_STAGE_2=FLAG{i_am_the_admin}
FLAG_STAGE_3=FLAG{knowledge_is_power}
FLAG_STAGE_4=FLAG{leaked_in_github}
FLAG_STAGE_5=FLAG{expert_hacker}
```

### 3. Run Development Server

```bash
# Start the backend server (runs on port 5001)
python scripts/dev_server.py
```

You should see:
```
AI Redteam CTF - Development Server
====================================================================
Server running at: http://localhost:5001
...
```

Note: Uses port 5001 to avoid conflict with macOS AirPlay Receiver on port 5000.

### 4. Serve the Frontend

In a separate terminal:

```bash
# Serve frontend files (runs on port 8000)
cd frontend
python -m http.server 8000
```

### 5. Access the Application

Open your browser and navigate to:
```
http://localhost:8000
```

You should see the CTF welcome screen. Enter your name and start playing!

## Testing the Application

### Test Checklist

- [ ] **Session Creation**: Enter name and click "Start CTF"
- [ ] **Basic Chat**: Send a regular message, verify AI responds
- [ ] **Slash Commands**: Try `/help`, `/hint`, `/stage`, `/reset`
- [ ] **Streaming**: Verify responses stream character-by-character
- [ ] **Stage 1**: Try to get the flag (hint: ask politely)
- [ ] **Flag Submission**: Use `/submit FLAG{...}` to advance
- [ ] **Stage Progression**: Verify advancing to stage 2 clears history
- [ ] **Session Export**: Click "Export Session" button
- [ ] **Session Import**: Import the exported JSON file
- [ ] **Error Handling**: Try invalid commands, check error messages

### Known Limitations (Local Development)

- Sessions are stored in memory and will be lost when the server restarts
- Only one server instance, so all users share the same session pool

## Deployment to AWS Lambda

### Prerequisites

1. Install AWS SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html
2. Configure AWS credentials: `aws configure`
3. Create an S3 bucket for SAM artifacts

### Step 1: Build Lambda Package

```bash
cd infrastructure
sam build
```

### Step 2: Deploy to AWS

```bash
sam deploy --guided
```

You'll be prompted for:
- Stack name (e.g., `ai-redteam-ctf-web`)
- AWS Region (e.g., `us-east-1`)
- Parameters:
  - AnthropicApiKey: Your Anthropic API key
  - FlagStage1 through FlagStage5: Your CTF flags

Answer the prompts:
- Confirm changes before deploy: Y
- Allow SAM CLI IAM role creation: Y
- Disable rollback: N
- Save arguments to configuration file: Y

### Step 3: Get Lambda Function URL

After deployment completes, note the `ApiUrl` in the outputs:

```
Outputs:
  ApiUrl: https://abc123xyz.lambda-url.us-east-1.on.aws/
```

### Step 4: Update Frontend

Edit `frontend/app.js` and update the API URL:

```javascript
// Change this line
const API_BASE_URL = 'http://localhost:5000';

// To this (use your actual Lambda URL)
const API_BASE_URL = 'https://abc123xyz.lambda-url.us-east-1.on.aws';
```

### Step 5: Deploy Frontend to S3

```bash
# Create S3 bucket
aws s3 mb s3://your-ctf-frontend-bucket

# Enable static website hosting
aws s3 website s3://your-ctf-frontend-bucket \
    --index-document index.html

# Make bucket public
aws s3api put-bucket-policy \
    --bucket your-ctf-frontend-bucket \
    --policy '{
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::your-ctf-frontend-bucket/*"
        }]
    }'

# Upload frontend files
cd frontend
aws s3 sync . s3://your-ctf-frontend-bucket/
```

### Step 6: Access Your CTF

Your CTF will be available at:
```
http://your-ctf-frontend-bucket.s3-website-us-east-1.amazonaws.com
```

For production, set up CloudFront for HTTPS and better performance.

## File Structure

```
AI-Redteam/
├── lambda/                      # Backend code
│   ├── lambda_handler.py        # Lambda entry point
│   ├── llm_core.py             # Core LLM logic
│   ├── session_manager.py      # Session management
│   ├── system_prompt.py        # Stage prompts
│   ├── knowledge_base.py       # RAG system
│   ├── knowledge/              # Knowledge files
│   └── requirements.txt        # Python dependencies
│
├── frontend/                    # Frontend code
│   ├── index.html              # Main UI
│   ├── app.js                  # Frontend logic
│   └── styles.css              # Styling
│
├── scripts/                     # Development tools
│   ├── dev_server.py           # Local dev server
│   └── requirements-dev.txt    # Dev dependencies
│
├── infrastructure/              # AWS deployment
│   ├── sam-template.yaml       # SAM template
│   └── samconfig.toml.example  # SAM config example
│
└── README-WEB.md               # This file
```

## Troubleshooting

### "Module not found" errors

Make sure you're running dev_server.py from the correct directory and that all Python dependencies are installed.

### SSE streaming not working

- Check browser console for errors
- Verify CORS is enabled on the backend
- Test with `curl` to see raw SSE output:
  ```bash
  curl "http://localhost:5001/api/chat/stream?sessionId=test&message=hello"
  ```

### Session expires immediately

Check that:
- Environment variables are loaded (check .env file)
- Anthropic API key is valid
- Backend server is running

### Lambda deployment fails

- Ensure AWS SAM CLI is installed and up to date
- Check AWS credentials are configured
- Verify S3 bucket for artifacts exists

## Cost Estimate

With Lambda and Haiku 4.5:
- Lambda Function URLs: Free
- Lambda compute: ~$0.000001667 per second
- Haiku 4.5 API: $0.10 per million input tokens, $0.50 per million output tokens

Estimated monthly cost for moderate usage (100 active users):
- Lambda: < $5
- Claude API: ~$10-20
- S3 + CloudFront: ~$1-5
- **Total: ~$15-30/month**

## Known Limitations

1. **Session Persistence**: Sessions are stored in memory and will be lost on Lambda cold starts (~15 min of inactivity)
2. **Concurrent Users**: Single Lambda instance handles all sessions; may hit memory limits with many concurrent users
3. **Timeout**: 15-minute max Lambda execution time
4. **Cold Starts**: First request after idle period takes 3-5 seconds

For production with high traffic, consider:
- ElastiCache Redis for session storage
- API Gateway + multiple Lambda instances for better scaling
- DynamoDB for persistent session storage

## Development vs Production

| Feature | Local Dev | AWS Lambda |
|---------|-----------|------------|
| Backend | Flask (port 5001) | Lambda Function URL |
| Frontend | http.server (port 8000) | S3 + CloudFront |
| Sessions | In-memory (Flask) | In-memory (Lambda) |
| Streaming | Flask SSE | Lambda Response Streaming |
| Cost | Free | Pay-per-use |

## Next Steps

1. Test locally with dev_server.py
2. Verify all 5 stages work correctly
3. Test export/import functionality
4. Deploy to AWS Lambda
5. Set up CloudFront for production (optional)
6. Monitor CloudWatch logs for errors
7. Set up alarms for API usage and Lambda errors

## Support

For issues or questions:
1. Check CloudWatch logs for Lambda errors
2. Test endpoints with `curl` to isolate frontend vs backend issues
3. Verify environment variables are set correctly
4. Check browser console for JavaScript errors

Happy hacking! 🚩
