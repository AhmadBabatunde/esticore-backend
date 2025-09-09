"""
Database models and operations for the Floor Plan Agent API
"""
import sqlite3
import hashlib
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from modules.config.settings import settings

@dataclass
class User:
    """User data model"""
    id: Optional[int] = None
    firstname: str = ""
    lastname: str = ""
    email: str = ""
    password: str = ""
    google_id: Optional[str] = None
    created_at: Optional[datetime] = None

@dataclass
class Project:
    """Project data model"""
    id: Optional[int] = None
    project_id: str = ""  # Unique project identifier
    name: str = ""
    description: str = ""
    user_id: int = 0
    doc_ids: Optional[List[str]] = None  # Associated document IDs as list
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class ChatMessage:
    """Chat message data model"""
    id: Optional[int] = None
    user_id: int = 0
    session_id: str = ""
    role: str = ""  # 'user' or 'assistant'
    message: str = ""
    timestamp: Optional[datetime] = None

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or settings.DATABASE_NAME
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_name)
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        # Create users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS userdata(
                id INTEGER PRIMARY KEY,
                firstname VARCHAR(255) NOT NULL,
                lastname VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                google_id VARCHAR(255) UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create chat history table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chathistory(
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES userdata (id)
            )
        """)
        
        # Create projects table (handle migration from doc_id to doc_ids)
        # First check if projects table exists and what columns it has
        cur.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cur.fetchall()]
        
        if not columns:  # Table doesn't exist, create new one
            cur.execute("""
                CREATE TABLE projects(
                    id INTEGER PRIMARY KEY,
                    project_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    user_id INTEGER NOT NULL,
                    doc_ids TEXT,  -- Store multiple document IDs as JSON array
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id)
                )
            """)
        elif 'doc_id' in columns and 'doc_ids' not in columns:
            # Migrate from old schema (doc_id) to new schema (doc_ids)
            self._migrate_projects_schema(cur)
        elif 'doc_ids' not in columns:
            # Add doc_ids column if it doesn't exist
            cur.execute("ALTER TABLE projects ADD COLUMN doc_ids TEXT")
        
        # Create test user if not exists
        cur.execute("SELECT * FROM userdata WHERE email = ?", ("test@example.com",))
        if not cur.fetchone():
            test_password = hashlib.sha256("testuser1".encode()).hexdigest()
            cur.execute(
                "INSERT INTO userdata (firstname, lastname, email, password) VALUES (?, ?, ?, ?)",
                ("Test", "User", "test@example.com", test_password)
            )
        
        conn.commit()
        conn.close()
    
    def _migrate_projects_schema(self, cur):
        """Migrate projects table from doc_id to doc_ids schema"""
        # Create new table with updated schema
        cur.execute("""
            CREATE TABLE projects_new(
                id INTEGER PRIMARY KEY,
                project_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                user_id INTEGER NOT NULL,
                doc_ids TEXT,  -- Store multiple document IDs as JSON array
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES userdata (id)
            )
        """)
        
        # Migrate data from old table to new table
        cur.execute("""
            INSERT INTO projects_new (id, project_id, name, description, user_id, doc_ids, created_at, updated_at)
            SELECT id, project_id, name, description, user_id, 
                   CASE 
                       WHEN doc_id IS NOT NULL THEN '["' || doc_id || '"]'
                       ELSE NULL
                   END as doc_ids,
                   created_at, updated_at
            FROM projects
        """)
        
        # Drop old table and rename new one
        cur.execute("DROP TABLE projects")
        cur.execute("ALTER TABLE projects_new RENAME TO projects")
    
    def create_user(self, firstname: str, lastname: str, email: str, password: str, google_id: str = None) -> int:
        """Create a new user"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "INSERT INTO userdata (firstname, lastname, email, password, google_id) VALUES (?, ?, ?, ?, ?)",
                (firstname, lastname, email, hashed_password, google_id)
            )
            conn.commit()
            
            # Get the new user's ID
            cur.execute("SELECT id FROM userdata WHERE email = ?", (email,))
            user = cur.fetchone()
            return user[0] if user else None
            
        finally:
            conn.close()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE email = ?",
                (email,)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    created_at=row[6]
                )
            return None
            
        finally:
            conn.close()
    
    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get user by Google ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE google_id = ?",
                (google_id,)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    created_at=row[6]
                )
            return None
            
        finally:
            conn.close()
    
    def verify_user_credentials(self, email: str, password: str) -> Optional[User]:
        """Verify user credentials"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE email = ? AND password = ?",
                (email, hashed_password)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    created_at=row[6]
                )
            return None
            
        finally:
            conn.close()
    
    def update_user_google_id(self, user_id: int, google_id: str):
        """Update user's Google ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("UPDATE userdata SET google_id = ? WHERE id = ?", (google_id, user_id))
            conn.commit()
        finally:
            conn.close()
    
    def add_chat_message(self, user_id: int, session_id: str, role: str, message: str):
        """Add a chat message to history"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "INSERT INTO chathistory (user_id, session_id, role, message) VALUES (?, ?, ?, ?)",
                (user_id, session_id, role, message)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_chat_history(self, user_id: int, session_id: str = None, limit: int = 50) -> List[ChatMessage]:
        """Get chat history for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if session_id:
                cur.execute("""
                    SELECT id, user_id, session_id, role, message, timestamp 
                    FROM chathistory 
                    WHERE user_id = ? AND session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (user_id, session_id, limit))
            else:
                cur.execute("""
                    SELECT id, user_id, session_id, role, message, timestamp 
                    FROM chathistory 
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (user_id, limit))
            
            rows = cur.fetchall()
            return [
                ChatMessage(
                    id=row[0],
                    user_id=row[1],
                    session_id=row[2],
                    role=row[3],
                    message=row[4],
                    timestamp=row[5]
                )
                for row in rows
            ]
            
        finally:
            conn.close()
    
    def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all unique session IDs for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT DISTINCT session_id, MAX(timestamp) as last_activity
                FROM chathistory 
                WHERE user_id = ?
                GROUP BY session_id
                ORDER BY last_activity DESC
            """, (user_id,))
            
            sessions = cur.fetchall()
            return [
                {
                    "session_id": session[0],
                    "last_activity": session[1]
                }
                for session in sessions
            ]
            
        finally:
            conn.close()
    
    # Project management methods
    def create_project(self, project_id: str, name: str, description: str, user_id: int, doc_ids: Optional[List[str]] = None) -> int:
        """Create a new project"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            # Convert doc_ids list to JSON string if present
            doc_ids_str = None
            if doc_ids and len(doc_ids) > 0:
                doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                "INSERT INTO projects (project_id, name, description, user_id, doc_ids) VALUES (?, ?, ?, ?, ?)",
                (project_id, name, description, user_id, doc_ids_str)
            )
            conn.commit()
            
            # Get the new project's ID
            cur.execute("SELECT id FROM projects WHERE project_id = ?", (project_id,))
            project = cur.fetchone()
            return project[0] if project else None
            
        finally:
            conn.close()
    
    def update_project_document(self, project_id: str, doc_ids: List[str]) -> bool:
        """Update the document IDs for a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            # Convert doc_ids list to JSON string
            doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                "UPDATE projects SET doc_ids = ? WHERE project_id = ?",
                (doc_ids_str, project_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def get_project_by_id(self, project_id: str) -> Optional[Project]:
        """Get project by project ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at 
                FROM projects 
                WHERE project_id = ?
            """, (project_id,))
            row = cur.fetchone()
            
            if row:
                # Parse doc_ids from JSON string if present
                doc_ids = None
                if row[5]:
                    try:
                        doc_ids = json.loads(row[5])
                    except json.JSONDecodeError:
                        doc_ids = [row[5]]  # Fallback to old single doc_id format
                
                return Project(
                    id=row[0],
                    project_id=row[1],
                    name=row[2],
                    description=row[3],
                    user_id=row[4],
                    doc_ids=doc_ids,
                    created_at=row[6],
                    updated_at=row[7]
                )
            return None
            
        finally:
            conn.close()
    
    def get_user_projects(self, user_id: int) -> List[Project]:
        """Get all projects for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at FROM projects WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            rows = cur.fetchall()
            
            result = []
            for row in rows:
                # Parse doc_ids from JSON string if present
                doc_ids = None
                if row[5]:
                    try:
                        doc_ids = json.loads(row[5])
                    except json.JSONDecodeError:
                        doc_ids = [row[5]]  # Fallback to old single doc_id format
                
                result.append(Project(
                    id=row[0],
                    project_id=row[1],
                    name=row[2],
                    description=row[3],
                    user_id=row[4],
                    doc_ids=doc_ids,
                    created_at=row[6],
                    updated_at=row[7]
                ))
            
            return result
            
        finally:
            conn.close()
    
    def update_project_details(self, project_id: str, name: str = None, description: str = None):
        """Update project details"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if name and description:
                cur.execute(
                    "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                    (name, description, project_id)
                )
            elif name:
                cur.execute(
                    "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                    (name, project_id)
                )
            elif description:
                cur.execute(
                    "UPDATE projects SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                    (description, project_id)
                )
            conn.commit()
        finally:
            conn.close()

# Global database manager instance
db_manager = DatabaseManager()