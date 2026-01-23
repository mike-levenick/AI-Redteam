"""
AWS Lambda handler for AI Redteam CTF web version.

Handles HTTP routing, SSE streaming, and session management.
"""

import json
import os
from typing import Dict, Any
from session_manager import SessionManager, SessionState
from llm_core import LLMCore


# Global session manager (survives across Lambda invocations)
session_manager = SessionManager()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda entry point"""

    # Clean up expired sessions
    session_manager.cleanup_expired_sessions()

    # Extract request info
    path = event.get('rawPath', '/')
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    query_params = event.get('queryStringParameters') or {}
    body = event.get('body', '')

    # Parse JSON body for POST requests
    try:
        if body and method == 'POST':
            body_data = json.loads(body)
        else:
            body_data = {}
    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON in request body")

    # Route requests
    if path == '/health' or path == '/api/health':
        return health_check()

    elif path == '/api/session/create' and method == 'POST':
        return create_session(body_data)

    elif path == '/api/chat/stream' and method == 'GET':
        # Simplified streaming - collect all chunks and return at once
        return handle_sse_stream(query_params)

    elif path == '/api/chat' and method == 'POST':
        return handle_chat(body_data)

    elif path == '/api/session/export' and method == 'POST':
        return export_session(body_data)

    elif path == '/api/session/import' and method == 'POST':
        return import_session(body_data)

    else:
        return error_response(404, f"Not found: {method} {path}")


def success_response(data: Any, status_code: int = 200) -> Dict[str, Any]:
    """Standard success response"""
    # Note: CORS headers are handled by Lambda Function URL config
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(data)
    }


def error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Standard error response"""
    # Note: CORS headers are handled by Lambda Function URL config
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'error': True,
            'message': message
        })
    }


def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return success_response({
        'status': 'healthy',
        'active_sessions': session_manager.get_session_count()
    })


def create_session(body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new session"""
    user_name = body.get('userName', 'Anonymous')

    # Create session
    session = session_manager.create_session(user_name)

    return success_response({
        'sessionId': session.session_id,
        'userName': session.user_name,
        'stage': session.stage
    })


def handle_sse_stream(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle SSE streaming endpoint - collects chunks and returns complete SSE response"""
    session_id = query_params.get('sessionId')
    message = query_params.get('message', '')

    if not session_id:
        return error_response(400, "Missing sessionId parameter")

    if not message:
        return error_response(400, "Missing message parameter")

    # Get session
    session = session_manager.get_session(session_id)
    if not session:
        return error_response(404, "Session not found or expired")

    # Create LLM core
    knowledge_dir = os.path.join(os.path.dirname(__file__), 'knowledge')
    llm_core = LLMCore(session, knowledge_dir=knowledge_dir)

    # Collect all streaming chunks
    sse_body = ""
    try:
        for chunk in llm_core.stream_llm_response(message):
            sse_body += chunk
    except Exception as e:
        # Return error as SSE event
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache'
            },
            'body': f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        }

    # Return complete SSE response
    # Note: CORS headers are handled by Lambda Function URL config
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache'
        },
        'body': sse_body
    }


def handle_chat(body: Dict[str, Any]) -> Dict[str, Any]:
    """Handle non-streaming chat (slash commands)"""
    session_id = body.get('sessionId')
    message = body.get('message', '')

    if not session_id:
        return error_response(400, "Missing sessionId")

    if not message:
        return error_response(400, "Missing message")

    # Get session
    session = session_manager.get_session(session_id)
    if not session:
        return error_response(404, "Session not found or expired")

    # Check if it's a slash command
    if not message.startswith('/'):
        return error_response(400, "Use /api/chat/stream for regular messages")

    # Create LLM core
    knowledge_dir = os.path.join(os.path.dirname(__file__), 'knowledge')
    llm_core = LLMCore(session, knowledge_dir=knowledge_dir)

    # Handle command
    result = llm_core.handle_slash_command(message)

    return success_response({
        'success': result['success'],
        'message': result['message'],
        'action': result.get('action'),
        'newStage': result.get('new_stage'),
        'currentStage': session.stage
    })


def export_session(body: Dict[str, Any]) -> Dict[str, Any]:
    """Export session state as JSON"""
    session_id = body.get('sessionId')

    if not session_id:
        return error_response(400, "Missing sessionId")

    # Get session data
    session_data = session_manager.export_session(session_id)
    if not session_data:
        return error_response(404, "Session not found")

    return success_response(session_data)


def import_session(body: Dict[str, Any]) -> Dict[str, Any]:
    """Import session from JSON data"""
    session_data = body.get('sessionData')

    if not session_data:
        return error_response(400, "Missing sessionData")

    try:
        # Import session (creates new session ID)
        session = session_manager.import_session(session_data)

        return success_response({
            'sessionId': session.session_id,
            'userName': session.user_name,
            'stage': session.stage,
            'message': 'Session imported successfully'
        })
    except Exception as e:
        return error_response(400, f"Failed to import session: {str(e)}")
