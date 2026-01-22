#!/usr/bin/env python3
"""
Local development server for AI Redteam CTF web version.

Mimics Lambda handler behavior for local testing.
Run this before deploying to AWS to test the full stack locally.
"""

import sys
import os
from pathlib import Path

# Add lambda directory to path
lambda_dir = Path(__file__).parent.parent / 'lambda'
sys.path.insert(0, str(lambda_dir))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, Response, jsonify, stream_with_context
from flask_cors import CORS
import json

from session_manager import SessionManager
from llm_core import LLMCore

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global session manager
session_manager = SessionManager()


@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'active_sessions': session_manager.get_session_count()
    })


@app.route('/api/session/create', methods=['POST'])
def create_session():
    """Create a new session"""
    data = request.json or {}
    user_name = data.get('userName', 'Anonymous')

    # Clean up expired sessions
    session_manager.cleanup_expired_sessions()

    # Create session
    session = session_manager.create_session(user_name)

    return jsonify({
        'sessionId': session.session_id,
        'userName': session.user_name,
        'stage': session.stage
    })


@app.route('/api/chat/stream', methods=['GET'])
def chat_stream():
    """SSE streaming endpoint"""
    session_id = request.args.get('sessionId')
    message = request.args.get('message', '')

    if not session_id:
        return jsonify({'error': 'Missing sessionId parameter'}), 400

    if not message:
        return jsonify({'error': 'Missing message parameter'}), 400

    # Get session
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found or expired'}), 404

    # Create LLM core
    knowledge_dir = lambda_dir / 'knowledge'
    llm_core = LLMCore(session, knowledge_dir=str(knowledge_dir))

    def generate():
        """Generator for SSE streaming"""
        try:
            for chunk in llm_core.stream_llm_response(message):
                yield chunk
        except Exception as e:
            error_chunk = f"data: {json.dumps(f'Error: {str(e)}')}\n\n"
            yield error_chunk
            yield "event: done\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering if behind nginx
        }
    )


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle non-streaming chat (slash commands)"""
    data = request.json or {}
    session_id = data.get('sessionId')
    message = data.get('message', '')

    if not session_id:
        return jsonify({'error': 'Missing sessionId'}), 400

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    # Get session
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found or expired'}), 404

    # Check if it's a slash command
    if not message.startswith('/'):
        return jsonify({'error': 'Use /api/chat/stream for regular messages'}), 400

    # Create LLM core
    knowledge_dir = lambda_dir / 'knowledge'
    llm_core = LLMCore(session, knowledge_dir=str(knowledge_dir))

    # Handle command
    result = llm_core.handle_slash_command(message)

    return jsonify({
        'success': result['success'],
        'message': result['message'],
        'action': result.get('action'),
        'newStage': result.get('new_stage'),
        'currentStage': session.stage
    })


@app.route('/api/session/export', methods=['POST'])
def export_session():
    """Export session state as JSON"""
    data = request.json or {}
    session_id = data.get('sessionId')

    if not session_id:
        return jsonify({'error': 'Missing sessionId'}), 400

    # Get session data
    session_data = session_manager.export_session(session_id)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(session_data)


@app.route('/api/session/import', methods=['POST'])
def import_session():
    """Import session from JSON data"""
    data = request.json or {}
    session_data = data.get('sessionData')

    if not session_data:
        return jsonify({'error': 'Missing sessionData'}), 400

    try:
        # Import session (creates new session ID)
        session = session_manager.import_session(session_data)

        return jsonify({
            'sessionId': session.session_id,
            'userName': session.user_name,
            'stage': session.stage,
            'message': 'Session imported successfully'
        })
    except Exception as e:
        return jsonify({'error': f'Failed to import session: {str(e)}'}), 400


if __name__ == '__main__':
    # Use port 5001 to avoid conflict with macOS AirPlay Receiver on 5000
    port = 5001

    print("=" * 64)
    print("AI Redteam CTF - Development Server")
    print("=" * 64)
    print()
    print(f"Server running at: http://localhost:{port}")
    print()
    print("API Endpoints:")
    print("  GET  /health                  - Health check")
    print("  POST /api/session/create      - Create new session")
    print("  GET  /api/chat/stream         - Stream chat responses (SSE)")
    print("  POST /api/chat                - Handle slash commands")
    print("  POST /api/session/export      - Export session")
    print("  POST /api/session/import      - Import session")
    print()
    print("Frontend: Open frontend/index.html in a browser")
    print("          (or serve with: python -m http.server 8000)")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 64)
    print()

    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
