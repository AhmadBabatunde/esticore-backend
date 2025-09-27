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
    is_verified: bool = False
    verification_token: Optional[str] = None
    verification_token_expires: Optional[datetime] = None
    created_at: Optional[datetime] = None

@dataclass
class EmailVerificationToken:
    """Email verification token data model"""
    id: Optional[int] = None
    user_id: int = 0
    token: str = ""
    expires_at: datetime = None
    created_at: Optional[datetime] = None
    used_at: Optional[datetime] = None

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
                    is_verified BOOLEAN DEFAULT FALSE,
                    verification_token VARCHAR(255),
                    verification_token_expires TIMESTAMP NULL,
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
                    vector_path TEXT,
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
                    is_verified BOOLEAN DEFAULT 0,
                    verification_token VARCHAR(255),
                    verification_token_expires DATETIME,
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
        self._migrate_email_verification_schema()
    
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
                        # MySQL TEXT columns cannot have default values
                        cur.execute("ALTER TABLE documents ADD COLUMN vector_path TEXT")
                        
                        # Update existing records with vector paths
                        cur.execute("SELECT doc_id FROM documents WHERE vector_path IS NULL")
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
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE email = {placeholder}",
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
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
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
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE google_id = {placeholder}",
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
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
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
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE email = {placeholder} AND password = {placeholder}",
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
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
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
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project record (cascades to project_documents)"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"DELETE FROM projects WHERE project_id = {placeholder}", (project_id,))
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
    
    def _migrate_email_verification_schema(self):
        """Add email verification columns to existing userdata table"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                # Check if email verification columns exist in MySQL
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = %s 
                    AND TABLE_NAME = 'userdata' 
                    AND COLUMN_NAME = 'is_verified'
                """, (settings.DB_NAME,))
                
                column_exists = cur.fetchone()[0] > 0
                
                if not column_exists:
                    print("Adding email verification columns to userdata table (MySQL)...")
                    cur.execute("ALTER TABLE userdata ADD COLUMN is_verified BOOLEAN DEFAULT FALSE")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token VARCHAR(255)")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token_expires TIMESTAMP NULL")
                    
                    # Set Google OAuth users as verified by default
                    cur.execute("UPDATE userdata SET is_verified = TRUE WHERE google_id IS NOT NULL")
                    
                    conn.commit()
                    print("Email verification columns added successfully")
                else:
                    print("Email verification columns already exist in userdata table")
            else:
                # Check if email verification columns exist in SQLite
                cur.execute("PRAGMA table_info(userdata)")
                columns = [row[1] for row in cur.fetchall()]
                
                if 'is_verified' not in columns:
                    print("Adding email verification columns to userdata table (SQLite)...")
                    cur.execute("ALTER TABLE userdata ADD COLUMN is_verified BOOLEAN DEFAULT 0")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token VARCHAR(255)")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token_expires DATETIME")
                    
                    # Set Google OAuth users as verified by default
                    cur.execute("UPDATE userdata SET is_verified = 1 WHERE google_id IS NOT NULL")
                    
                    conn.commit()
                    print("Email verification columns added successfully")
                else:
                    print("Email verification columns already exist in userdata table")
                    
        except Exception as e:
            print(f"Email verification migration error: {e}")
            if conn:
                conn.rollback()
            # Don't raise the exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    # Email verification methods
    def create_verification_token(self, user_id: int, token: str, expires_at: datetime) -> bool:
        """Create or update verification token for user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"UPDATE userdata SET verification_token = {placeholder}, verification_token_expires = {placeholder} WHERE id = {placeholder}",
                (token, expires_at, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    
    def get_user_by_verification_token(self, token: str) -> Optional[User]:
        """Get user by verification token"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE verification_token = {placeholder}",
                (token,)
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
                    is_verified=bool(row[6]),
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
            return None
            
        finally:
            conn.close()
    
    def verify_user_email(self, user_id: int) -> bool:
        """Mark user email as verified and clear verification token"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"UPDATE userdata SET is_verified = {1 if not self.use_rds else 'TRUE'}, verification_token = NULL, verification_token_expires = NULL WHERE id = {placeholder}",
                (user_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    
    def clear_expired_verification_tokens(self):
        """Clear expired verification tokens"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if self.use_rds:
                cur.execute(
                    "UPDATE userdata SET verification_token = NULL, verification_token_expires = NULL WHERE verification_token_expires < NOW()"
                )
            else:
                cur.execute(
                    "UPDATE userdata SET verification_token = NULL, verification_token_expires = NULL WHERE verification_token_expires < datetime('now')"
                )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
    # Add these methods to your existing DatabaseManager class

    def create_admin_user(self, username: str, email: str, password: str, is_super_admin: bool = False) -> int:
        """Create a new admin user"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO admin_users (username, email, password, is_super_admin) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (username, email, hashed_password, is_super_admin)
            )
            conn.commit()
            
            cur.execute(f"SELECT id FROM admin_users WHERE email = {placeholder}", (email,))
            admin = cur.fetchone()
            return admin[0] if admin else None
        finally:
            conn.close()

    def verify_admin_credentials(self, email: str, password: str) -> Optional[AdminUser]:
        """Verify admin credentials"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, username, email, password, is_super_admin, created_at, last_login FROM admin_users WHERE email = {placeholder} AND password = {placeholder}",
                (email, hashed_password)
            )
            row = cur.fetchone()
            
            if row:
                return AdminUser(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    password=row[3],
                    is_super_admin=bool(row[4]),
                    created_at=row[5],
                    last_login=row[6]
                )
            return None
        finally:
            conn.close()

    def get_all_users(self) -> List[User]:
        """Get all users in the system"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                SELECT id, firstname, lastname, email, password, google_id, is_verified, 
                    verification_token, verification_token_expires, created_at 
                FROM userdata 
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            
            return [
                User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
                for row in rows
            ]
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> bool:
        """Delete a user and all their data"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Delete user (cascades to related tables due to foreign keys)
            cur.execute(f"DELETE FROM userdata WHERE id = {placeholder}", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_user_status(self, user_id: int, is_active: bool) -> bool:
        """Update user active status"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"UPDATE userdata SET is_active = {placeholder} WHERE id = {placeholder}",
                (is_active, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # Add similar methods for subscription plans, feedback, storage, etc.
    # Add these methods to your existing DatabaseManager class

    # Admin methods
    def get_admin_by_email(self, email: str) -> Optional[AdminUser]:
        """Get admin by email"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, username, email, password, is_super_admin, created_at, last_login FROM admin_users WHERE email = {placeholder}",
                (email,)
            )
            row = cur.fetchone()
            
            if row:
                return AdminUser(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    password=row[3],
                    is_super_admin=bool(row[4]),
                    created_at=row[5],
                    last_login=row[6]
                )
            return None
        finally:
            conn.close()

    def update_admin_last_login(self, admin_id: int):
        """Update admin last login timestamp"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE id = {placeholder}", (admin_id,))
            else:
                cur.execute(f"UPDATE admin_users SET last_login = datetime('now') WHERE id = {placeholder}", (admin_id,))
            conn.commit()
        finally:
            conn.close()

    def get_super_admins(self) -> List[AdminUser]:
        """Get all super admins"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT id, username, email, password, is_super_admin, created_at, last_login FROM admin_users WHERE is_super_admin = TRUE")
            rows = cur.fetchall()
            
            return [
                AdminUser(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    password=row[3],
                    is_super_admin=bool(row[4]),
                    created_at=row[5],
                    last_login=row[6]
                )
                for row in rows
            ]
        finally:
            conn.close()

    # Subscription plan methods
    def create_subscription_plan(self, name: str, description: str, price_monthly: float, price_annual: float,
                            storage_gb: int, project_limit: int, user_limit: int, action_limit: int,
                            features: List[str], has_free_trial: bool, trial_days: int) -> int:
        """Create a new subscription plan"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Convert features list to JSON
            features_json = json.dumps(features) if features else "[]"
            
            cur.execute(
                f"INSERT INTO subscription_plans (name, description, price_monthly, price_annual, storage_gb, project_limit, user_limit, action_limit, features, has_free_trial, trial_days) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (name, description, price_monthly, price_annual, storage_gb, project_limit, user_limit, action_limit, features_json, has_free_trial, trial_days)
            )
            conn.commit()
            
            cur.execute(f"SELECT id FROM subscription_plans WHERE name = {placeholder}", (name,))
            plan = cur.fetchone()
            return plan[0] if plan else None
        finally:
            conn.close()

    def get_all_subscription_plans(self) -> List[SubscriptionPlan]:
        """Get all subscription plans"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT id, name, description, price_monthly, price_annual, storage_gb, project_limit, user_limit, action_limit, features, is_active, has_free_trial, trial_days, created_at FROM subscription_plans ORDER BY price_monthly ASC")
            rows = cur.fetchall()
            
            plans = []
            for row in rows:
                # Parse features from JSON
                features = []
                if row[9]:
                    try:
                        features = json.loads(row[9])
                    except json.JSONDecodeError:
                        features = []
                
                plans.append(SubscriptionPlan(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    price_monthly=float(row[3]) if row[3] else 0.0,
                    price_annual=float(row[4]) if row[4] else 0.0,
                    storage_gb=row[5],
                    project_limit=row[6],
                    user_limit=row[7],
                    action_limit=row[8],
                    features=features,
                    is_active=bool(row[10]),
                    has_free_trial=bool(row[11]),
                    trial_days=row[12],
                    created_at=row[13]
                ))
            return plans
        finally:
            conn.close()

    def get_subscription_plan_by_id(self, plan_id: int) -> Optional[SubscriptionPlan]:
        """Get subscription plan by ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute("SELECT id, name, description, price_monthly, price_annual, storage_gb, project_limit, user_limit, action_limit, features, is_active, has_free_trial, trial_days, created_at FROM subscription_plans WHERE id = ?", (plan_id,))
            row = cur.fetchone()
            
            if row:
                # Parse features from JSON
                features = []
                if row[9]:
                    try:
                        features = json.loads(row[9])
                    except json.JSONDecodeError:
                        features = []
                
                return SubscriptionPlan(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    price_monthly=float(row[3]) if row[3] else 0.0,
                    price_annual=float(row[4]) if row[4] else 0.0,
                    storage_gb=row[5],
                    project_limit=row[6],
                    user_limit=row[7],
                    action_limit=row[8],
                    features=features,
                    is_active=bool(row[10]),
                    has_free_trial=bool(row[11]),
                    trial_days=row[12],
                    created_at=row[13]
                )
            return None
        finally:
            conn.close()

    def update_subscription_plan(self, plan_id: int, name: str = None, description: str = None,
                            price_monthly: float = None, price_annual: float = None,
                            storage_gb: int = None, project_limit: int = None,
                            user_limit: int = None, action_limit: int = None,
                            features: List[str] = None, is_active: bool = None) -> bool:
        """Update subscription plan"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            update_fields = []
            params = []
            
            if name is not None:
                update_fields.append("name = ?")
                params.append(name)
            if description is not None:
                update_fields.append("description = ?")
                params.append(description)
            if price_monthly is not None:
                update_fields.append("price_monthly = ?")
                params.append(price_monthly)
            if price_annual is not None:
                update_fields.append("price_annual = ?")
                params.append(price_annual)
            if storage_gb is not None:
                update_fields.append("storage_gb = ?")
                params.append(storage_gb)
            if project_limit is not None:
                update_fields.append("project_limit = ?")
                params.append(project_limit)
            if user_limit is not None:
                update_fields.append("user_limit = ?")
                params.append(user_limit)
            if action_limit is not None:
                update_fields.append("action_limit = ?")
                params.append(action_limit)
            if features is not None:
                features_json = json.dumps(features)
                update_fields.append("features = ?")
                params.append(features_json)
            if is_active is not None:
                update_fields.append("is_active = ?")
                params.append(is_active)
            
            if not update_fields:
                return False
            
            if self.use_rds:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
            else:
                update_fields.append("updated_at = datetime('now')")
            
            params.append(plan_id)
            
            query = f"UPDATE subscription_plans SET {', '.join(update_fields)} WHERE id = ?"
            cur.execute(query, params)
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_subscription_plan(self, plan_id: int) -> bool:
        """Delete subscription plan"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"DELETE FROM subscription_plans WHERE id = {placeholder}", (plan_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # User storage methods
    def create_user_storage(self, user_id: int) -> bool:
        """Create user storage record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO user_storage (user_id, used_storage_mb) VALUES ({placeholder}, 0)",
                (user_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            # Handle duplicate key error
            if "Duplicate" in str(e) or "UNIQUE constraint" in str(e):
                return False
            raise
        finally:
            conn.close()

    def get_user_storage(self, user_id: int) -> Optional[UserStorage]:
        """Get user storage"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, user_id, used_storage_mb, last_updated FROM user_storage WHERE user_id = {placeholder}",
                (user_id,)
            )
            row = cur.fetchone()
            
            if row:
                return UserStorage(
                    id=row[0],
                    user_id=row[1],
                    used_storage_mb=row[2],
                    last_updated=row[3]
                )
            return None
        finally:
            conn.close()

    def update_user_storage(self, user_id: int, used_storage_mb: int) -> bool:
        """Update user storage"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(
                    f"UPDATE user_storage SET used_storage_mb = {placeholder}, last_updated = CURRENT_TIMESTAMP WHERE user_id = {placeholder}",
                    (used_storage_mb, user_id)
                )
            else:
                cur.execute(
                    f"UPDATE user_storage SET used_storage_mb = {placeholder}, last_updated = datetime('now') WHERE user_id = {placeholder}",
                    (used_storage_mb, user_id)
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # Feedback methods
    def create_feedback(self, user_id: int, email: str, ai_response: str, rating: str, project_name: str = None) -> int:
        """Create feedback record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO feedback (user_id, email, ai_response, rating, project_name) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (user_id, email, ai_response, rating, project_name)
            )
            conn.commit()
            
            cur.execute(f"SELECT id FROM feedback WHERE user_id = {placeholder} ORDER BY created_at DESC LIMIT 1", (user_id,))
            feedback = cur.fetchone()
            return feedback[0] if feedback else None
        finally:
            conn.close()

    def get_all_feedback(self, page: int = 1, limit: int = 20, rating: str = None) -> List[Feedback]:
        """Get all feedback with pagination"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            offset = (page - 1) * limit
            query = "SELECT id, user_id, email, ai_response, rating, project_name, created_at FROM feedback"
            params = []
            
            if rating:
                query += f" WHERE rating = {placeholder}"
                params.append(rating)
            
            query += f" ORDER BY created_at DESC LIMIT {placeholder} OFFSET {placeholder}"
            params.extend([limit, offset])
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            return [
                Feedback(
                    id=row[0],
                    user_id=row[1],
                    email=row[2],
                    ai_response=row[3],
                    rating=row[4],
                    project_name=row[5],
                    created_at=row[6]
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_feedback_statistics(self) -> Dict[str, int]:
        """Get feedback statistics"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating")
            rows = cur.fetchall()
            
            stats = {'total': 0, 'positive': 0, 'negative': 0}
            for row in rows:
                stats[row[0]] = row[1]
                stats['total'] += row[1]
            
            return stats
        finally:
            conn.close()

    # AI model methods
    def create_ai_model(self, name: str, provider: str, model_name: str, config: Dict[str, Any], is_active: bool = False) -> int:
        """Create AI model record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            config_json = json.dumps(config) if config else "{}"
            
            cur.execute(
                f"INSERT INTO ai_models (name, provider, model_name, is_active, config) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (name, provider, model_name, is_active, config_json)
            )
            conn.commit()
            
            cur.execute(f"SELECT id FROM ai_models WHERE name = {placeholder}", (name,))
            model = cur.fetchone()
            return model[0] if model else None
        finally:
            conn.close()

    def get_all_ai_models(self) -> List[AIModel]:
        """Get all AI models"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT id, name, provider, model_name, is_active, config, created_at FROM ai_models ORDER BY created_at DESC")
            rows = cur.fetchall()
            
            models = []
            for row in rows:
                # Parse config from JSON
                config = {}
                if row[5]:
                    try:
                        config = json.loads(row[5])
                    except json.JSONDecodeError:
                        config = {}
                
                models.append(AIModel(
                    id=row[0],
                    name=row[1],
                    provider=row[2],
                    model_name=row[3],
                    is_active=bool(row[4]),
                    config=config,
                    created_at=row[6]
                ))
            return models
        finally:
            conn.close()

    def activate_ai_model(self, model_id: int) -> bool:
        """Activate an AI model and deactivate others"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # First deactivate all models
            cur.execute(f"UPDATE ai_models SET is_active = FALSE")
            
            # Activate the specified model
            cur.execute(f"UPDATE ai_models SET is_active = TRUE WHERE id = {placeholder}", (model_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_active_ai_model(self) -> Optional[AIModel]:
        """Get the active AI model"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT id, name, provider, model_name, is_active, config, created_at FROM ai_models WHERE is_active = TRUE LIMIT 1")
            row = cur.fetchone()
            
            if row:
                # Parse config from JSON
                config = {}
                if row[5]:
                    try:
                        config = json.loads(row[5])
                    except json.JSONDecodeError:
                        config = {}
                
                return AIModel(
                    id=row[0],
                    name=row[1],
                    provider=row[2],
                    model_name=row[3],
                    is_active=bool(row[4]),
                    config=config,
                    created_at=row[6]
                )
            return None
        finally:
            conn.close()

    # Recently viewed projects methods
    def add_recently_viewed_project(self, user_id: int, project_id: str) -> bool:
        """Add or update recently viewed project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Try to update existing record
            if self.use_rds:
                cur.execute(f"""
                    INSERT INTO recently_viewed_projects (user_id, project_id, view_count) 
                    VALUES ({placeholder}, {placeholder}, 1)
                    ON DUPLICATE KEY UPDATE view_count = view_count + 1, viewed_at = CURRENT_TIMESTAMP
                """, (user_id, project_id))
            else:
                cur.execute(f"""
                    INSERT OR REPLACE INTO recently_viewed_projects (user_id, project_id, view_count, viewed_at) 
                    VALUES ({placeholder}, {placeholder}, 
                    COALESCE((SELECT view_count FROM recently_viewed_projects WHERE user_id = {placeholder} AND project_id = {placeholder}), 0) + 1,
                    CURRENT_TIMESTAMP)
                """, (user_id, project_id, user_id, project_id))
            
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_recently_viewed_projects(self, user_id: int, limit: int = 10) -> List[RecentlyViewedProject]:
        """Get user's recently viewed projects"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT rvp.id, rvp.user_id, rvp.project_id, rvp.viewed_at, rvp.view_count, p.name as project_name
                FROM recently_viewed_projects rvp
                JOIN projects p ON rvp.project_id = p.project_id
                WHERE rvp.user_id = {placeholder}
                ORDER BY rvp.viewed_at DESC
                LIMIT {placeholder}
            """, (user_id, limit))
            
            rows = cur.fetchall()
            
            return [
                RecentlyViewedProject(
                    id=row[0],
                    user_id=row[1],
                    project_id=row[2],
                    viewed_at=row[3],
                    view_count=row[4],
                    project_name=row[5] if len(row) > 5 else ""
                )
                for row in rows
            ]
        finally:
            conn.close()

    # User subscription methods
    def create_user_subscription(self, user_id: int, plan_id: int, stripe_subscription_id: str = None,
                            stripe_customer_id: str = None, interval: str = "monthly") -> int:
        """Create user subscription"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                INSERT INTO user_subscriptions (user_id, plan_id, stripe_subscription_id, stripe_customer_id, interval) 
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (user_id, plan_id, stripe_subscription_id, stripe_customer_id, interval))
            conn.commit()
            
            cur.execute(f"SELECT id FROM user_subscriptions WHERE user_id = {placeholder} ORDER BY created_at DESC LIMIT 1", (user_id,))
            subscription = cur.fetchone()
            return subscription[0] if subscription else None
        finally:
            conn.close()

    def get_user_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Get user's active subscription"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT us.id, us.user_id, us.plan_id, us.stripe_subscription_id, us.stripe_customer_id,
                    us.current_period_start, us.current_period_end, us.status, us.interval, 
                    us.auto_renew, us.is_active, us.created_at, us.updated_at,
                    sp.name, sp.description, sp.storage_gb, sp.project_limit, sp.action_limit
                FROM user_subscriptions us
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.user_id = {placeholder} AND us.is_active = TRUE
                ORDER BY us.created_at DESC
                LIMIT 1
            """, (user_id,))
            
            row = cur.fetchone()
            if row:
                # This would return a combined object with subscription and plan info
                # You might want to adjust this based on your needs
                return UserSubscription(
                    id=row[0],
                    user_id=row[1],
                    plan_id=row[2],
                    stripe_subscription_id=row[3],
                    stripe_customer_id=row[4],
                    current_period_start=row[5],
                    current_period_end=row[6],
                    status=row[7],
                    interval=row[8],
                    auto_renew=bool(row[9]),
                    is_active=bool(row[10]),
                    created_at=row[11],
                    updated_at=row[12]
                )
            return None
        finally:
            conn.close()

    def update_user_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Update user subscription"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            update_fields = []
            params = []
            
            for key, value in kwargs.items():
                if value is not None:
                    update_fields.append(f"{key} = ?")
                    params.append(value)
            
            if not update_fields:
                return False
            
            if self.use_rds:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
            else:
                update_fields.append("updated_at = datetime('now')")
            
            params.append(subscription_id)
            
            query = f"UPDATE user_subscriptions SET {', '.join(update_fields)} WHERE id = ?"
            cur.execute(query, params)
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # Dashboard statistics methods
    def get_total_users_count(self, status: str = None, search: str = None) -> int:
        """Get total users count with optional filtering"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            query = "SELECT COUNT(*) FROM userdata WHERE 1=1"
            params = []
            
            if status:
                query += f" AND is_active = {placeholder}"
                params.append(status == "active")
            
            if search:
                query += f" AND (email LIKE {placeholder} OR firstname LIKE {placeholder} OR lastname LIKE {placeholder})"
                search_term = f"%{search}%"
                params.extend([search_term, search_term, search_term])
            
            cur.execute(query, params)
            return cur.fetchone()[0]
        finally:
            conn.close()

    def get_active_users_count(self) -> int:
        """Get count of active users"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT COUNT(*) FROM userdata WHERE is_active = TRUE")
            return cur.fetchone()[0]
        finally:
            conn.close()

    def get_total_feedback_count(self) -> int:
        """Get total feedback count"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT COUNT(*) FROM feedback")
            return cur.fetchone()[0]
        finally:
            conn.close()

    def get_recent_signups(self, days: int = 7) -> int:
        """Get recent signups count"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"SELECT COUNT(*) FROM userdata WHERE created_at >= DATE_SUB(NOW(), INTERVAL {placeholder} DAY)", (days,))
            else:
                cur.execute(f"SELECT COUNT(*) FROM userdata WHERE created_at >= datetime('now', '-{placeholder} days')", (days,))
            return cur.fetchone()[0]
        finally:
            conn.close()

    def get_total_storage_usage(self) -> int:
        """Get total storage usage in MB"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT SUM(used_storage_mb) FROM user_storage")
            result = cur.fetchone()[0]
            return result if result else 0
        finally:
            conn.close()

    def get_subscriptions_expiring_soon(self, days: int) -> List[Dict]:
        """Get subscriptions expiring soon"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"""
                    SELECT us.id, u.email, sp.name, us.current_period_end 
                    FROM user_subscriptions us
                    JOIN userdata u ON us.user_id = u.id
                    JOIN subscription_plans sp ON us.plan_id = sp.id
                    WHERE us.is_active = TRUE 
                    AND us.current_period_end BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL {placeholder} DAY)
                """, (days,))
            else:
                cur.execute(f"""
                    SELECT us.id, u.email, sp.name, us.current_period_end 
                    FROM user_subscriptions us
                    JOIN userdata u ON us.user_id = u.id
                    JOIN subscription_plans sp ON us.plan_id = sp.id
                    WHERE us.is_active = TRUE 
                    AND us.current_period_end BETWEEN datetime('now') AND datetime('now', '+{placeholder} days')
                """, (days,))
            
            rows = cur.fetchall()
            return [
                {
                    "subscription_id": row[0],
                    "user_email": row[1],
                    "plan_name": row[2],
                    "expiry_date": row[3]
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_recently_expired_subscriptions(self, days: int) -> List[Dict]:
        """Get recently expired subscriptions"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"""
                    SELECT us.id, u.email, sp.name, us.current_period_end 
                    FROM user_subscriptions us
                    JOIN userdata u ON us.user_id = u.id
                    JOIN subscription_plans sp ON us.plan_id = sp.id
                    WHERE us.is_active = TRUE 
                    AND us.current_period_end BETWEEN DATE_SUB(NOW(), INTERVAL {placeholder} DAY) AND NOW()
                """, (days,))
            else:
                cur.execute(f"""
                    SELECT us.id, u.email, sp.name, us.current_period_end 
                    FROM user_subscriptions us
                    JOIN userdata u ON us.user_id = u.id
                    JOIN subscription_plans sp ON us.plan_id = sp.id
                    WHERE us.is_active = TRUE 
                    AND us.current_period_end BETWEEN datetime('now', '-{placeholder} days') AND datetime('now')
                """, (days,))
            
            rows = cur.fetchall()
            return [
                {
                    "subscription_id": row[0],
                    "user_email": row[1],
                    "plan_name": row[2],
                    "expiry_date": row[3]
                }
                for row in rows
            ]
        finally:
            conn.close()
# Global database manager instance
db_manager = DatabaseManager()
