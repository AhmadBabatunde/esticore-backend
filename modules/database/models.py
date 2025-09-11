"""
Database models and operations for the Floor Plan Agent API
"""
import os
import sqlite3
import mysql.connector
from mysql.connector import Error as MySQLError
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
class Document:
    """Document data model"""
    id: Optional[int] = None
    doc_id: str = ""  # Unique document identifier (UUID)
    filename: str = ""
    pdf_path: str = ""
    vector_path: str = ""  # Path to FAISS vector store directory
    pages: int = 0
    chunks_indexed: int = 0
    status: str = "active"  # active, file_missing, error
    user_id: int = 0  # Owner of the document
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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
        self.use_rds = settings.USE_RDS
        
        if self.use_rds:
            self.mysql_config = {
                'host': settings.DB_HOST,
                'port': settings.DB_PORT,
                'database': settings.DB_NAME,
                'user': settings.DB_USER,
                'password': settings.DB_PASSWORD,
                'autocommit': False,
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                # Connection pooling and timeout settings
                'pool_name': 'esticore_pool',
                'pool_size': 10,
                'pool_reset_session': True,
                'connect_timeout': 30,
                'sql_mode': 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'
            }
        
        self.init_database()
    
    def get_connection(self):
        """Get database connection with retry logic and proper error handling"""
        if self.use_rds:
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    return mysql.connector.connect(**self.mysql_config)
                except MySQLError as e:
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to connect to MySQL after {max_retries} attempts: {e}")
                    
                    # Handle specific connection errors
                    if e.errno in [2003, 2013, 2006]:  # Connection errors
                        import time
                        print(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise Exception(f"MySQL connection error: {e}")
                except Exception as e:
                    raise Exception(f"Unexpected database connection error: {e}")
        else:
            return sqlite3.connect(self.db_name)
    
    def execute_with_retry(self, query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
        """Execute query with connection retry logic and proper error handling"""
        max_retries = 3
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                
                if params:
                    cur.execute(query, params)
                else:
                    cur.execute(query)
                
                if fetch_one:
                    result = cur.fetchone()
                elif fetch_all:
                    result = cur.fetchall()
                else:
                    result = cur.rowcount
                
                conn.commit()
                return result
                
            except MySQLError as e:
                if conn:
                    conn.rollback()
                
                # Handle specific MySQL errors that might be retryable
                if e.errno in [2006, 2013, 1205, 1213] and attempt < max_retries - 1:  # Connection lost, deadlock
                    import time
                    time.sleep(0.5 * (attempt + 1))  # Progressive delay
                    continue
                else:
                    raise Exception(f"MySQL query error: {e}")
            except Exception as e:
                if conn:
                    conn.rollback()
                raise Exception(f"Database query error: {e}")
            finally:
                if conn:
                    conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        if self.use_rds:
            # MySQL table creation statements
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userdata(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    firstname VARCHAR(255) NOT NULL,
                    lastname VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    google_id VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create chat history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chathistory(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    session_id TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    user_id INT NOT NULL,
                    doc_ids TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create documents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    doc_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    pdf_path TEXT NOT NULL,
                    vector_path TEXT NOT NULL,
                    pages INT DEFAULT 0,
                    chunks_indexed INT DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active',
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_doc_id (doc_id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create project_documents junction table for many-to-many relationship
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id VARCHAR(255) NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE KEY unique_project_document (project_id, doc_id),
                    INDEX idx_project_id (project_id),
                    INDEX idx_doc_id (doc_id)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create test user if not exists
            cur.execute("SELECT * FROM userdata WHERE email = %s", ("test@example.com",))
            if not cur.fetchone():
                test_password = hashlib.sha256("testuser1".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO userdata (firstname, lastname, email, password) VALUES (%s, %s, %s, %s)",
                    ("Test", "User", "test@example.com", test_password)
                )
        else:
            # SQLite table creation statements (legacy)
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
            
            # Create documents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id INTEGER PRIMARY KEY,
                    doc_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    vector_path TEXT NOT NULL,
                    pages INTEGER DEFAULT 0,
                    chunks_indexed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    user_id INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id)
                )
            """)
            
            # Create indexes for documents table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)")
            
            # Create project_documents junction table for many-to-many relationship
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE (project_id, doc_id)
                )
            """)
            
            # Create indexes for project_documents table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents (project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_doc_id ON project_documents (doc_id)")
            
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
        
        # Run migration for existing databases
        self._migrate_documents_schema()
    
    def _migrate_documents_schema(self):
        """Migrate documents table to include vector_path column if it doesn't exist"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                # Check if documents table exists first
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = %s 
                    AND TABLE_NAME = 'documents'
                """, (settings.DB_NAME,))
                
                table_exists = cur.fetchone()[0] > 0
                
                if table_exists:
                    # Check if vector_path column exists in MySQL
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'documents' 
                        AND COLUMN_NAME = 'vector_path'
                    """, (settings.DB_NAME,))
                    
                    column_exists = cur.fetchone()[0] > 0
                    
                    if not column_exists:
                        print("Adding vector_path column to documents table (MySQL)...")
                        cur.execute("ALTER TABLE documents ADD COLUMN vector_path TEXT NOT NULL DEFAULT ''")
                        
                        # Update existing records with vector paths
                        cur.execute("SELECT doc_id FROM documents WHERE vector_path = '' OR vector_path IS NULL")
                        docs_to_update = cur.fetchall()
                        
                        for (doc_id,) in docs_to_update:
                            vector_path = os.path.join(settings.VECTORS_DIR, doc_id)
                            cur.execute("UPDATE documents SET vector_path = %s WHERE doc_id = %s", (vector_path, doc_id))
                        
                        conn.commit()
                        print(f"Updated {len(docs_to_update)} documents with vector paths")
                    else:
                        print("vector_path column already exists in documents table")
            else:
                # Check if documents table exists first for SQLite
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
                table_exists = cur.fetchone() is not None
                
                if table_exists:
                    # Check if vector_path column exists in SQLite
                    cur.execute("PRAGMA table_info(documents)")
                    columns = [row[1] for row in cur.fetchall()]
                    
                    if 'vector_path' not in columns:
                        print("Adding vector_path column to documents table (SQLite)...")
                        cur.execute("ALTER TABLE documents ADD COLUMN vector_path TEXT NOT NULL DEFAULT ''")
                        
                        # Update existing records with vector paths
                        cur.execute("SELECT doc_id FROM documents WHERE vector_path = '' OR vector_path IS NULL")
                        docs_to_update = cur.fetchall()
                        
                        for (doc_id,) in docs_to_update:
                            vector_path = os.path.join(settings.VECTORS_DIR, doc_id)
                            cur.execute("UPDATE documents SET vector_path = ? WHERE doc_id = ?", (vector_path, doc_id))
                        
                        conn.commit()
                        print(f"Updated {len(docs_to_update)} documents with vector paths")
                    else:
                        print("vector_path column already exists in documents table")
                        
        except Exception as e:
            print(f"Migration error: {e}")
            if conn:
                conn.rollback()
            # Don't raise the exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    def _get_placeholder(self):
        """Get the appropriate parameter placeholder for the database type"""
        return "%s" if self.use_rds else "?"
    
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO userdata (firstname, lastname, email, password, google_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (firstname, lastname, email, hashed_password, google_id)
            )
            conn.commit()
            
            # Get the new user's ID
            cur.execute(f"SELECT id FROM userdata WHERE email = {placeholder}", (email,))
            user = cur.fetchone()
            return user[0] if user else None
            
        finally:
            conn.close()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE email = {placeholder}",
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE google_id = {placeholder}",
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, created_at FROM userdata WHERE email = {placeholder} AND password = {placeholder}",
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"UPDATE userdata SET google_id = {placeholder} WHERE id = {placeholder}", (google_id, user_id))
            conn.commit()
        finally:
            conn.close()
    
    def add_chat_message(self, user_id: int, session_id: str, role: str, message: str):
        """Add a chat message to history"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO chathistory (user_id, session_id, role, message) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (user_id, session_id, role, message)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_chat_history(self, user_id: int, session_id: str = None, limit: int = 50) -> List[ChatMessage]:
        """Get chat history for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if session_id:
                if self.use_rds:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp 
                        FROM chathistory 
                        WHERE user_id = %s AND session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, session_id, limit))
                else:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp 
                        FROM chathistory 
                        WHERE user_id = ? AND session_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (user_id, session_id, limit))
            else:
                if self.use_rds:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp 
                        FROM chathistory 
                        WHERE user_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, limit))
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT DISTINCT session_id, MAX(timestamp) as last_activity
                FROM chathistory 
                WHERE user_id = {placeholder}
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
        placeholder = self._get_placeholder()
        
        try:
            # Convert doc_ids list to JSON string if present
            doc_ids_str = None
            if doc_ids and len(doc_ids) > 0:
                doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                f"INSERT INTO projects (project_id, name, description, user_id, doc_ids) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (project_id, name, description, user_id, doc_ids_str)
            )
            conn.commit()
            
            # Get the new project's ID
            cur.execute(f"SELECT id FROM projects WHERE project_id = {placeholder}", (project_id,))
            project = cur.fetchone()
            return project[0] if project else None
            
        finally:
            conn.close()
    
    def update_project_document(self, project_id: str, doc_ids: List[str]) -> bool:
        """Update the document IDs for a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Convert doc_ids list to JSON string
            doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                f"UPDATE projects SET doc_ids = {placeholder} WHERE project_id = {placeholder}",
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at 
                FROM projects 
                WHERE project_id = {placeholder}
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
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at FROM projects WHERE user_id = {placeholder} ORDER BY created_at DESC",
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
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                # MySQL syntax for updating timestamp
                if name and description:
                    cur.execute(
                        f"UPDATE projects SET name = {placeholder}, description = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (name, description, project_id)
                    )
                elif name:
                    cur.execute(
                        f"UPDATE projects SET name = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (name, project_id)
                    )
                elif description:
                    cur.execute(
                        f"UPDATE projects SET description = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (description, project_id)
                    )
            else:
                # SQLite syntax
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
    
    # Document management methods
    def create_document(self, doc_id: str, filename: str, pdf_path: str, vector_path: str, pages: int, chunks_indexed: int, user_id: int) -> int:
        """Create a new document record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO documents (doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, user_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, user_id)
            )
            conn.commit()
            
            # Get the new document's ID
            cur.execute(f"SELECT id FROM documents WHERE doc_id = {placeholder}", (doc_id,))
            document = cur.fetchone()
            return document[0] if document else None
            
        finally:
            conn.close()
    
    def get_document_by_doc_id(self, doc_id: str) -> Optional[Document]:
        """Get document by doc_id"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT id, doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, status, user_id, created_at, updated_at 
                FROM documents 
                WHERE doc_id = {placeholder}
            """, (doc_id,))
            row = cur.fetchone()
            
            if row:
                return Document(
                    id=row[0],
                    doc_id=row[1],
                    filename=row[2],
                    pdf_path=row[3],
                    vector_path=row[4],
                    pages=row[5],
                    chunks_indexed=row[6],
                    status=row[7],
                    user_id=row[8],
                    created_at=row[9],
                    updated_at=row[10]
                )
            return None
            
        finally:
            conn.close()
    
    def get_user_documents(self, user_id: int) -> List[Document]:
        """Get all documents for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, status, user_id, created_at, updated_at FROM documents WHERE user_id = {placeholder} ORDER BY created_at DESC",
                (user_id,)
            )
            rows = cur.fetchall()
            
            return [
                Document(
                    id=row[0],
                    doc_id=row[1],
                    filename=row[2],
                    pdf_path=row[3],
                    vector_path=row[4],
                    pages=row[5],
                    chunks_indexed=row[6],
                    status=row[7],
                    user_id=row[8],
                    created_at=row[9],
                    updated_at=row[10]
                )
                for row in rows
            ]
            
        finally:
            conn.close()
    
    def get_all_documents(self) -> List[Document]:
        """Get all documents in the system"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT id, doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, status, user_id, created_at, updated_at 
                FROM documents 
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            
            return [
                Document(
                    id=row[0],
                    doc_id=row[1],
                    filename=row[2],
                    pdf_path=row[3],
                    vector_path=row[4],
                    pages=row[5],
                    chunks_indexed=row[6],
                    status=row[7],
                    user_id=row[8],
                    created_at=row[9],
                    updated_at=row[10]
                )
                for row in rows
            ]
            
        finally:
            conn.close()
    
    def update_document_status(self, doc_id: str, status: str) -> bool:
        """Update document status"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(
                    f"UPDATE documents SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE doc_id = {placeholder}",
                    (status, doc_id)
                )
            else:
                cur.execute(
                    "UPDATE documents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE doc_id = ?",
                    (status, doc_id)
                )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def update_document_pages(self, doc_id: str, pages: int) -> bool:
        """Update document page count"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(
                    f"UPDATE documents SET pages = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE doc_id = {placeholder}",
                    (pages, doc_id)
                )
            else:
                cur.execute(
                    "UPDATE documents SET pages = ?, updated_at = CURRENT_TIMESTAMP WHERE doc_id = ?",
                    (pages, doc_id)
                )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"DELETE FROM documents WHERE doc_id = {placeholder}", (doc_id,))
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    # Project-Document relationship methods
    def add_document_to_project(self, project_id: str, doc_id: str) -> bool:
        """Add a document to a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO project_documents (project_id, doc_id) VALUES ({placeholder}, {placeholder})",
                (project_id, doc_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            # Handle duplicate key error gracefully
            if "Duplicate" in str(e) or "UNIQUE constraint" in str(e):
                return False  # Already exists
            raise e
        finally:
            conn.close()
    
    def remove_document_from_project(self, project_id: str, doc_id: str) -> bool:
        """Remove a document from a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"DELETE FROM project_documents WHERE project_id = {placeholder} AND doc_id = {placeholder}",
                (project_id, doc_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def get_project_documents(self, project_id: str) -> List[Document]:
        """Get all documents for a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT d.id, d.doc_id, d.filename, d.pdf_path, d.vector_path, d.pages, d.chunks_indexed, d.status, d.user_id, d.created_at, d.updated_at 
                FROM documents d
                INNER JOIN project_documents pd ON d.doc_id = pd.doc_id
                WHERE pd.project_id = {placeholder}
                ORDER BY pd.created_at ASC
            """, (project_id,))
            rows = cur.fetchall()
            
            return [
                Document(
                    id=row[0],
                    doc_id=row[1],
                    filename=row[2],
                    pdf_path=row[3],
                    vector_path=row[4],
                    pages=row[5],
                    chunks_indexed=row[6],
                    status=row[7],
                    user_id=row[8],
                    created_at=row[9],
                    updated_at=row[10]
                )
                for row in rows
            ]
            
        finally:
            conn.close()
    
    def get_document_projects(self, doc_id: str) -> List[Project]:
        """Get all projects that contain a specific document"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT p.id, p.project_id, p.name, p.description, p.user_id, p.doc_ids, p.created_at, p.updated_at 
                FROM projects p
                INNER JOIN project_documents pd ON p.project_id = pd.project_id
                WHERE pd.doc_id = {placeholder}
                ORDER BY p.created_at DESC
            """, (doc_id,))
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

# Global database manager instance
db_manager = DatabaseManager()