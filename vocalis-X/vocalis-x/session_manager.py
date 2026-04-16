"""
Thread-safe session management for Vocalis-X
Replaces global variables with proper session storage
"""
import threading
import time
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
import uuid


class SessionData:
    """Data stored for each session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.last_instrumental_path: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
    
    def touch(self):
        """Update last accessed time"""
        self.last_accessed = datetime.now()
    
    def is_expired(self, timeout_minutes: int = 60) -> bool:
        """Check if session has expired"""
        expiry_time = self.last_accessed + timedelta(minutes=timeout_minutes)
        return datetime.now() > expiry_time
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "last_instrumental_path": self.last_instrumental_path,
            "metadata": self.metadata
        }


class SessionManager:
    """Thread-safe session manager"""
    
    def __init__(self, timeout_minutes: int = 60):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.RLock()
        self._timeout_minutes = timeout_minutes
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session and return session ID"""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        with self._lock:
            self._sessions[session_id] = SessionData(session_id)
        
        return session_id
    
    def get_session(self, session_id: str, create_if_missing: bool = True) -> Optional[SessionData]:
        """Get session data by ID"""
        with self._lock:
            session = self._sessions.get(session_id)
            
            if session is None and create_if_missing:
                session_id = self.create_session(session_id)
                session = self._sessions[session_id]
            
            if session:
                session.touch()
            
            return session
    
    def set_last_instrumental(self, session_id: str, path: str):
        """Store last instrumental path for session"""
        session = self.get_session(session_id)
        if session:
            session.last_instrumental_path = path
    
    def get_last_instrumental(self, session_id: str) -> Optional[str]:
        """Get last instrumental path for session"""
        session = self.get_session(session_id, create_if_missing=False)
        if session:
            return session.last_instrumental_path
        return None
    
    def set_metadata(self, session_id: str, key: str, value: Any):
        """Store metadata for session"""
        session = self.get_session(session_id)
        if session:
            session.metadata[key] = value
    
    def get_metadata(self, session_id: str, key: str, default: Any = None) -> Any:
        """Get metadata for session"""
        session = self.get_session(session_id, create_if_missing=False)
        if session:
            return session.metadata.get(key, default)
        return default
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions and return count removed"""
        with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired(self._timeout_minutes)
            ]
            
            for sid in expired:
                del self._sessions[sid]
            
            return len(expired)
    
    def get_all_sessions(self) -> Dict[str, SessionData]:
        """Get all active sessions (for debugging)"""
        with self._lock:
            return self._sessions.copy()
    
    def clear_all(self):
        """Clear all sessions (for testing)"""
        with self._lock:
            self._sessions.clear()


# Global session manager instance
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Get the global session manager"""
    return _session_manager
