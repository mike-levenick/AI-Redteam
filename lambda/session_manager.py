"""
Session management for AI Redteam CTF web version.

Provides in-memory session storage with TTL cleanup.
"""

import time
import secrets
from dataclasses import dataclass, asdict, field
from typing import Dict, Optional, List


@dataclass
class SessionState:
    """Represents the state of a user session"""
    session_id: str
    user_name: str
    stage: int
    conversation_history: List[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def to_dict(self):
        """Convert session state to dictionary for export"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        """Restore session state from dictionary"""
        return cls(**data)


class SessionManager:
    """Manages in-memory session storage with TTL cleanup"""

    # Session expires after 1 hour of inactivity
    MAX_SESSION_AGE = 3600

    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}

    def create_session(self, user_name: str = "Anonymous") -> SessionState:
        """Create a new session with unique ID"""
        session_id = f"sess_{secrets.token_urlsafe(16)}"

        session = SessionState(
            session_id=session_id,
            user_name=user_name,
            stage=1,
            conversation_history=[],
            created_at=time.time(),
            last_accessed=time.time()
        )

        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get session by ID, update last_accessed timestamp"""
        session = self.sessions.get(session_id)
        if session:
            session.last_accessed = time.time()
        return session

    def update_session(self, session_id: str, session_state: SessionState):
        """Update session state"""
        session_state.last_accessed = time.time()
        self.sessions[session_id] = session_state

    def delete_session(self, session_id: str):
        """Delete a specific session"""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def cleanup_expired_sessions(self):
        """Remove sessions older than MAX_SESSION_AGE"""
        current_time = time.time()
        expired = [
            sid for sid, state in self.sessions.items()
            if current_time - state.last_accessed > self.MAX_SESSION_AGE
        ]
        for sid in expired:
            del self.sessions[sid]
        return len(expired)

    def get_session_count(self) -> int:
        """Get total number of active sessions"""
        return len(self.sessions)

    def export_session(self, session_id: str) -> Optional[dict]:
        """Export session state as dictionary for download"""
        session = self.sessions.get(session_id)
        if session:
            return session.to_dict()
        return None

    def import_session(self, data: dict) -> SessionState:
        """Import session from dictionary, create new session ID"""
        # Create new session ID to avoid conflicts
        new_session_id = f"sess_{secrets.token_urlsafe(16)}"

        session = SessionState(
            session_id=new_session_id,
            user_name=data.get('user_name', 'Anonymous'),
            stage=data.get('stage', 1),
            conversation_history=data.get('conversation_history', []),
            created_at=time.time(),
            last_accessed=time.time()
        )

        self.sessions[new_session_id] = session
        return session
