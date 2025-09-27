"""
Database models and operations for the Floor Plan Agent API
"""
import os
import sqlite3
import mysql.connector
from mysql.connector import Error as MySQLError
import psycopg2
from psycopg2 import Error as PostgreSQLError
from psycopg2.extras import RealDictCursor
import hashlib
import json
import uuid
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
    file_id: str = ""  # Reference to file_storage table
    pages: int = 0
    chunks_indexed: int = 0
    status: str = "active"  # active, file_missing, error
    user_id: int = 0  # Owner of the document
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate document data"""
        if not self.doc_id or not self.filename:
            return False
        if not self.file_id:  # file_id is required for database storage
            return False
        if self.pages < 0 or self.chunks_indexed < 0:
            return False
        if self.status not in ['active', 'file_missing', 'error', 'processing']:
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'doc_id': self.doc_id,
            'filename': self.filename,
            'file_id': self.file_id,
            'pages': self.pages,
            'chunks_indexed': self.chunks_indexed,
            'status': self.status,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

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
class ChatSession:
    """Enhanced chat session data model with context support"""
    id: Optional[int] = None
    session_id: str = ""
    user_id: int = 0
    context_type: str = ""  # PROJECT, DOCUMENT, GENERAL
    context_id: Optional[str] = None  # project_id, doc_id, or None for general
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None  # Additional context data

@dataclass
class ChatMessage:
    """Enhanced chat message data model with context support"""
    id: Optional[int] = None
    user_id: int = 0
    session_id: str = ""
    role: str = ""  # 'user' or 'assistant'
    message: str = ""
    timestamp: Optional[datetime] = None
    context_type: Optional[str] = None  # PROJECT, DOCUMENT, GENERAL
    context_id: Optional[str] = None  # project_id, doc_id, or None for general

@dataclass
class FileStorage:
    """File storage data model for binary file storage in database"""
    id: Optional[int] = None
    file_id: str = ""
    filename: str = ""
    content_type: str = ""
    file_size: int = 0
    file_data: bytes = b""
    user_id: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate file storage data"""
        if not self.file_id or not self.filename:
            return False
        if not self.content_type or not isinstance(self.file_data, bytes):
            return False
        if self.file_size != len(self.file_data):
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding binary data"""
        result = {
            'id': self.id,
            'file_id': self.file_id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        if include_data:
            result['file_data'] = self.file_data
        return result

@dataclass
class VectorChunk:
    """Vector chunk data model for pgvector storage"""
    id: Optional[int] = None
    chunk_id: str = ""
    doc_id: str = ""
    page_number: int = 0
    chunk_text: str = ""
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate vector chunk data"""
        if not self.chunk_id or not self.doc_id:
            return False
        if not self.chunk_text.strip():
            return False
        if self.page_number < 1:
            return False
        if self.embedding and len(self.embedding) != 1536:  # OpenAI embedding dimension
            return False
        return True
    
    def to_dict(self, include_embedding: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding embedding vector"""
        result = {
            'id': self.id,
            'chunk_id': self.chunk_id,
            'doc_id': self.doc_id,
            'page_number': self.page_number,
            'chunk_text': self.chunk_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_embedding and self.embedding:
            result['embedding'] = self.embedding
        return result

@dataclass
class GeneratedOutput:
    """Generated output data model for storing processed files"""
    id: Optional[int] = None
    output_id: str = ""
    filename: str = ""
    content_type: str = ""
    file_size: int = 0
    file_data: bytes = b""
    source_doc_id: Optional[str] = None
    user_id: int = 0
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate generated output data"""
        if not self.output_id or not self.filename:
            return False
        if not self.content_type or not isinstance(self.file_data, bytes):
            return False
        if self.file_size != len(self.file_data):
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding binary data"""
        result = {
            'id': self.id,
            'output_id': self.output_id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'source_doc_id': self.source_doc_id,
            'user_id': self.user_id,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_data:
            result['file_data'] = self.file_data
        return result

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or settings.DATABASE_NAME
        self.use_rds = settings.USE_RDS
        
        # Determine database type based on port
        self.is_postgres = settings.DB_PORT == 5432
        
        if self.use_rds:
            if self.is_postgres:
                self.postgres_config = {
                    'host': settings.DB_HOST,
                    'port': settings.DB_PORT,
                    'database': settings.DB_NAME,
                    'user': settings.DB_USER,
                    'password': settings.DB_PASSWORD,
                    'connect_timeout': 30
                }
            else:
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
                    if self.is_postgres:
                        return psycopg2.connect(**self.postgres_config)
                    else:
                        return mysql.connector.connect(**self.mysql_config)
                except (PostgreSQLError, MySQLError) as e:
                    if attempt == max_retries - 1:
                        db_type = "PostgreSQL" if self.is_postgres else "MySQL"
                        raise Exception(f"Failed to connect to {db_type} after {max_retries} attempts: {e}")
                    
                    # Handle specific connection errors
                    import time
                    print(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
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
                if self.is_postgres:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                else:
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
                
            except (PostgreSQLError, MySQLError) as e:
                if conn:
                    conn.rollback()
                
                # Handle specific database errors that might be retryable
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))  # Progressive delay
                    continue
                else:
                    db_type = "PostgreSQL" if self.is_postgres else "MySQL"
                    raise Exception(f"{db_type} query error: {e}")
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
        
        if self.use_rds and self.is_postgres:
            # PostgreSQL table creation statements
            print("Initializing PostgreSQL database...")
            
            # Ensure pgvector extension is available
            self.ensure_pgvector_extension()
            
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userdata(
                    id SERIAL PRIMARY KEY,
                    firstname VARCHAR(255) NOT NULL,
                    lastname VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    google_id VARCHAR(255) UNIQUE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    verification_token VARCHAR(255),
                    verification_token_expires TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create chat history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chathistory(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context_type VARCHAR(20) CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id VARCHAR(255),
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chathistory
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
            
            # Create projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects(
                    id SERIAL PRIMARY KEY,
                    project_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    user_id INTEGER NOT NULL,
                    doc_ids TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create documents table (updated schema)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id SERIAL PRIMARY KEY,
                    doc_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    file_id VARCHAR(255),
                    pages INTEGER DEFAULT 0,
                    chunks_indexed INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active',
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for documents
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)")
            
            # Create project_documents junction table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id SERIAL PRIMARY KEY,
                    project_id VARCHAR(255) NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE (project_id, doc_id)
                )
            """)
            
            # Create indexes for project_documents
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents (project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_doc_id ON project_documents (doc_id)")
            
            # Create chat_sessions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    context_type VARCHAR(20) NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chat_sessions
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_active ON chat_sessions (user_id, is_active)")
            
            conn.commit()
            
            # Create new tables for file and vector storage
            self.create_new_tables()
            
            # Migrate documents table if needed
            self.migrate_documents_table()
            
            # Create test user if not exists
            cur.execute("SELECT * FROM userdata WHERE email = %s", ("test@example.com",))
            if not cur.fetchone():
                test_password = hashlib.sha256("testuser1".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO userdata (firstname, lastname, email, password) VALUES (%s, %s, %s, %s)",
                    ("Test", "User", "test@example.com", test_password)
                )
                
        elif self.use_rds:
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
                    context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NULL,
                    context_id VARCHAR(255) NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_context (context_type, context_id)
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
            
            # Create chat_sessions table for enhanced session management
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NOT NULL,
                    context_id VARCHAR(255) NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    metadata JSON NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE,
                    INDEX idx_user_context (user_id, context_type, context_id),
                    INDEX idx_session_id (session_id),
                    INDEX idx_last_activity (last_activity),
                    INDEX idx_active_sessions (user_id, is_active)
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
                    context_type TEXT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL') OR context_type IS NULL),
                    context_id TEXT NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata (id)
                )
            """)
            
            # Create indexes for chathistory table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
            
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
            
            # Create chat_sessions table for enhanced session management
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id INTEGER PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    context_type TEXT NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id TEXT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chat_sessions table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_active ON chat_sessions (user_id, is_active)")
            
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
        self._migrate_session_schema()
    
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
        if self.use_rds:
            return "%s" if not self.is_postgres else "%s"
        return "?"
    
    def ensure_pgvector_extension(self) -> bool:
        """Ensure pgvector extension is available in PostgreSQL"""
        if not self.is_postgres:
            return True  # Not needed for non-PostgreSQL databases
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Try to create the extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
            
            # Verify the extension is available
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            result = cur.fetchone()
            
            if result:
                print("pgvector extension is available")
                return True
            else:
                print("WARNING: pgvector extension could not be created")
                return False
                
        except Exception as e:
            print(f"Error setting up pgvector extension: {e}")
            print("Please install pgvector extension manually:")
            print("1. Connect to your PostgreSQL database as superuser")
            print("2. Run: CREATE EXTENSION vector;")
            return False
        finally:
            if conn:
                conn.close()
    
    def create_new_tables(self):
        """Create new tables for file storage and vector operations"""
        if not self.is_postgres:
            print("New table creation is only supported for PostgreSQL")
            return
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Create file_storage table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS file_storage (
                    id SERIAL PRIMARY KEY,
                    file_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_data BYTEA NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for file_storage
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_storage_file_id ON file_storage (file_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_storage_user_id ON file_storage (user_id)")
            
            # Create vector_chunks table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    id SERIAL PRIMARY KEY,
                    chunk_id VARCHAR(255) UNIQUE NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    page_number INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for vector_chunks
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_doc_id ON vector_chunks (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_page_number ON vector_chunks (page_number)")
            
            # Create vector similarity index (only if pgvector is available)
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding ON vector_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
            except Exception as e:
                print(f"Could not create vector index (pgvector may not be available): {e}")
            
            # Create generated_outputs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS generated_outputs (
                    id SERIAL PRIMARY KEY,
                    output_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_data BYTEA NOT NULL,
                    source_doc_id VARCHAR(255),
                    user_id INTEGER NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_doc_id) REFERENCES documents(doc_id) ON DELETE SET NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for generated_outputs
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_output_id ON generated_outputs (output_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_source_doc_id ON generated_outputs (source_doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_user_id ON generated_outputs (user_id)")
            
            conn.commit()
            print("Successfully created new tables for file and vector storage")
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error creating new tables: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def migrate_documents_table(self):
        """Migrate documents table to remove file paths and add file_id"""
        if not self.is_postgres:
            print("Documents table migration is only supported for PostgreSQL")
            return
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Check if file_id column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'documents' AND column_name = 'file_id'
            """)
            
            if not cur.fetchone():
                # Add file_id column
                cur.execute("ALTER TABLE documents ADD COLUMN file_id VARCHAR(255)")
                
                # Add foreign key constraint
                cur.execute("""
                    ALTER TABLE documents 
                    ADD CONSTRAINT fk_documents_file_id 
                    FOREIGN KEY (file_id) REFERENCES file_storage(file_id) ON DELETE SET NULL
                """)
                
                print("Added file_id column to documents table")
            
            # Check if old columns exist and remove them
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'documents' AND column_name IN ('pdf_path', 'vector_path')
            """)
            
            old_columns = cur.fetchall()
            for column in old_columns:
                column_name = column[0] if isinstance(column, tuple) else column['column_name']
                cur.execute(f"ALTER TABLE documents DROP COLUMN IF EXISTS {column_name}")
                print(f"Removed {column_name} column from documents table")
            
            conn.commit()
            print("Successfully migrated documents table")
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error migrating documents table: {e}")
            # Don't raise exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    # File storage operations
    def store_file(self, file_id: str, filename: str, content_type: str, file_data: bytes, user_id: int) -> bool:
        """Store file as binary data in database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        # Validate input parameters
        if not file_id or not filename or not content_type:
            raise ValueError("file_id, filename, and content_type are required")
        if not isinstance(file_data, bytes):
            raise ValueError("file_data must be bytes")
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO file_storage (file_id, filename, content_type, file_size, file_data, user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (file_id, filename, content_type, len(file_data), file_data, user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing file: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_file(self, file_id: str) -> Optional[FileStorage]:
        """Retrieve file from database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, file_id, filename, content_type, file_size, file_data, user_id, created_at, updated_at
                FROM file_storage WHERE file_id = %s
            """, (file_id,))
            
            row = cur.fetchone()
            if row:
                # Convert memoryview to bytes if needed
                file_data = row['file_data']
                if isinstance(file_data, memoryview):
                    file_data = file_data.tobytes()
                
                return FileStorage(
                    id=row['id'],
                    file_id=row['file_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=file_data,
                    user_id=row['user_id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None
            
        except Exception as e:
            raise Exception(f"Error retrieving file: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM file_storage WHERE file_id = %s", (file_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting file: {e}")
        finally:
            if conn:
                conn.close()
    
    # Vector storage operations
    def store_vector_chunks(self, doc_id: str, chunks: List[Dict[str, Any]]) -> int:
        """Store vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            stored_count = 0
            for chunk in chunks:
                chunk_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO vector_chunks (chunk_id, doc_id, page_number, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    doc_id,
                    chunk.get('page', 1),
                    chunk.get('text', ''),
                    chunk.get('embedding')
                ))
                stored_count += 1
            
            conn.commit()
            return stored_count
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_vector_chunks(self, doc_id: str) -> List[VectorChunk]:
        """Get all vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, chunk_id, doc_id, page_number, chunk_text, embedding, created_at
                FROM vector_chunks WHERE doc_id = %s ORDER BY page_number, id
            """, (doc_id,))
            
            chunks = []
            for row in cur.fetchall():
                chunks.append(VectorChunk(
                    id=row['id'],
                    chunk_id=row['chunk_id'],
                    doc_id=row['doc_id'],
                    page_number=row['page_number'],
                    chunk_text=row['chunk_text'],
                    embedding=row['embedding'],
                    created_at=row['created_at']
                ))
            
            return chunks
            
        except Exception as e:
            raise Exception(f"Error retrieving vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    def similarity_search(self, doc_id: str, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Perform similarity search using pgvector"""
        if not self.is_postgres:
            raise Exception("Vector similarity search is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Convert embedding to string format for PostgreSQL
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            cur.execute("""
                SELECT chunk_id, doc_id, page_number, chunk_text, 
                       embedding <=> %s::vector as distance
                FROM vector_chunks 
                WHERE doc_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (embedding_str, doc_id, embedding_str, k))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'chunk_id': row['chunk_id'],
                    'doc_id': row['doc_id'],
                    'page': row['page_number'],
                    'text': row['chunk_text'],
                    'distance': float(row['distance']),
                    'similarity_score': 1 - float(row['distance'])  # Convert distance to similarity
                })
            
            return results
            
        except Exception as e:
            raise Exception(f"Error performing similarity search: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_vector_chunks(self, doc_id: str) -> bool:
        """Delete all vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM vector_chunks WHERE doc_id = %s", (doc_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    # Generated output operations
    def store_generated_output(self, output_id: str, filename: str, content_type: str, 
                              file_data: bytes, source_doc_id: str, user_id: int, 
                              metadata: Dict[str, Any] = None) -> bool:
        """Store generated output file"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO generated_outputs (output_id, filename, content_type, file_size, 
                                             file_data, source_doc_id, user_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (output_id, filename, content_type, len(file_data), file_data, 
                  source_doc_id, user_id, json.dumps(metadata) if metadata else None))
            
            conn.commit()
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing generated output: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_generated_output(self, output_id: str) -> Optional[GeneratedOutput]:
        """Retrieve generated output from database"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, output_id, filename, content_type, file_size, file_data, 
                       source_doc_id, user_id, metadata, created_at
                FROM generated_outputs WHERE output_id = %s
            """, (output_id,))
            
            row = cur.fetchone()
            if row:
                # Convert memoryview to bytes if needed
                file_data = row['file_data']
                if isinstance(file_data, memoryview):
                    file_data = file_data.tobytes()
                
                return GeneratedOutput(
                    id=row['id'],
                    output_id=row['output_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=file_data,
                    source_doc_id=row['source_doc_id'],
                    user_id=row['user_id'],
                    metadata=row['metadata'] if row['metadata'] else None,  # JSONB is already parsed
                    created_at=row['created_at']
                )
            return None
            
        except Exception as e:
            raise Exception(f"Error retrieving generated output: {e}")
        finally:
            if conn:
                conn.close()
    
    def list_generated_outputs(self, user_id: int = None) -> List[GeneratedOutput]:
        """List generated outputs, optionally filtered by user"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            if user_id:
                cur.execute("""
                    SELECT id, output_id, filename, content_type, file_size, 
                           source_doc_id, user_id, metadata, created_at
                    FROM generated_outputs WHERE user_id = %s ORDER BY created_at DESC
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT id, output_id, filename, content_type, file_size, 
                           source_doc_id, user_id, metadata, created_at
                    FROM generated_outputs ORDER BY created_at DESC
                """)
            
            outputs = []
            for row in cur.fetchall():
                outputs.append(GeneratedOutput(
                    id=row['id'],
                    output_id=row['output_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=b"",  # Don't load file data for listing
                    source_doc_id=row['source_doc_id'],
                    user_id=row['user_id'],
                    metadata=row['metadata'] if row['metadata'] else None,  # JSONB is already parsed
                    created_at=row['created_at']
                ))
            
            return outputs
            
        except Exception as e:
            raise Exception(f"Error listing generated outputs: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_generated_output(self, output_id: str) -> bool:
        """Delete generated output from database"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM generated_outputs WHERE output_id = %s", (output_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting generated output: {e}")
        finally:
            if conn:
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
    
    def add_chat_message(self, user_id: int, session_id: str, role: str, message: str, context_type: str = None, context_id: str = None):
        """Add a chat message to history with optional context information"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                INSERT INTO chathistory (user_id, session_id, role, message, context_type, context_id) 
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (user_id, session_id, role, message, context_type, context_id))
            
            conn.commit()
            
            # Update session activity if session exists
            self.update_session_activity(session_id)
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
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = %s AND session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, session_id, limit))
                else:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = ? AND session_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (user_id, session_id, limit))
            else:
                if self.use_rds:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, limit))
                else:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
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
                    timestamp=row[5],
                    context_type=row[6],
                    context_id=row[7]
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
    
    def get_project_session(self, user_id: int, project_id: str) -> Optional[str]:
        """Get the most recent session ID associated with a specific project for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Search for chat messages that mention the project ID
            # This looks for messages that contain the project ID in the content
            cur.execute(f"""
                SELECT session_id, MAX(timestamp) as last_activity
                FROM chathistory 
                WHERE user_id = {placeholder} 
                AND (message LIKE {placeholder} OR message LIKE {placeholder})
                GROUP BY session_id
                ORDER BY last_activity DESC
                LIMIT 1
            """, (user_id, f"%Project ID: {project_id}%", f"%project_id%{project_id}%"))
            
            row = cur.fetchone()
            return row[0] if row else None
            
        except Exception as e:
            # If there's an error, return None to fall back to creating a new session
            return None
        finally:
            conn.close()
    
    # Enhanced session management methods
    def create_chat_session(self, session_id: str, user_id: int, context_type: str, context_id: str = None, metadata: Dict[str, Any] = None) -> bool:
        """Create a new chat session with context support"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            
            cur.execute(f"""
                INSERT INTO chat_sessions (session_id, user_id, context_type, context_id, metadata)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (session_id, user_id, context_type, context_id, metadata_json))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error creating chat session: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_session_by_id(self, session_id: str) -> Optional[ChatSession]:
        """Get session by session ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT id, session_id, user_id, context_type, context_id, is_active, 
                       created_at, last_activity, metadata
                FROM chat_sessions 
                WHERE session_id = {placeholder}
            """, (session_id,))
            
            row = cur.fetchone()
            if row:
                metadata = json.loads(row[8]) if row[8] else None
                return ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                )
            return None
        finally:
            conn.close()
    
    def get_session_by_context(self, user_id: int, context_type: str, context_id: str = None) -> Optional[ChatSession]:
        """Get the most recent active session for a specific context"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if context_id is None:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder} AND context_id IS NULL
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                    LIMIT 1
                """, (user_id, context_type))
            else:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder} AND context_id = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                    LIMIT 1
                """, (user_id, context_type, context_id))
            
            row = cur.fetchone()
            if row:
                metadata = json.loads(row[8]) if row[8] else None
                return ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                )
            return None
        finally:
            conn.close()
    
    def get_active_sessions(self, user_id: int, context_type: str = None) -> List[ChatSession]:
        """Get all active sessions for a user, optionally filtered by context type"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if context_type:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                """, (user_id, context_type))
            else:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                """, (user_id,))
            
            rows = cur.fetchall()
            sessions = []
            for row in rows:
                metadata = json.loads(row[8]) if row[8] else None
                sessions.append(ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                ))
            return sessions
        finally:
            conn.close()
    
    def update_session_activity(self, session_id: str) -> bool:
        """Update the last activity timestamp for a session"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                # MySQL automatically updates last_activity with ON UPDATE CURRENT_TIMESTAMP
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET last_activity = CURRENT_TIMESTAMP 
                    WHERE session_id = {placeholder}
                """, (session_id,))
            else:
                # SQLite needs manual timestamp update
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET last_activity = CURRENT_TIMESTAMP 
                    WHERE session_id = {placeholder}
                """, (session_id,))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error updating session activity: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def deactivate_session(self, session_id: str) -> bool:
        """Mark a session as inactive"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                UPDATE chat_sessions 
                SET is_active = {'FALSE' if self.use_rds else '0'}
                WHERE session_id = {placeholder}
            """, (session_id,))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error deactivating session: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def cleanup_expired_sessions(self, hours: int = 24) -> int:
        """Mark sessions as inactive if they haven't been active for the specified hours"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET is_active = FALSE
                    WHERE is_active = TRUE 
                    AND last_activity < NOW() - INTERVAL '{placeholder} hours'
                """, (hours,))
            else:
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET is_active = 0
                    WHERE is_active = 1 
                    AND datetime(last_activity, '+{placeholder} hours') < datetime('now')
                """, (hours,))
            
            conn.commit()
            cleaned_count = cur.rowcount
            print(f"Cleaned up {cleaned_count} expired sessions")
            return cleaned_count
        except Exception as e:
            print(f"Error cleaning up expired sessions: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()
    
    def add_chat_message_with_context(self, user_id: int, session_id: str, role: str, message: str, context_type: str = None, context_id: str = None):
        """Add a chat message to history with context information"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                INSERT INTO chathistory (user_id, session_id, role, message, context_type, context_id) 
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (user_id, session_id, role, message, context_type, context_id))
            
            conn.commit()
            
            # Update session activity
            self.update_session_activity(session_id)
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
    def create_document(self, doc_id: str, filename: str, file_id: str, pages: int, chunks_indexed: int, user_id: int, pdf_path: str = None, vector_path: str = None) -> int:
        """Create a new document record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(
                    f"INSERT INTO documents (doc_id, filename, file_id, pages, chunks_indexed, user_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (doc_id, filename, file_id, pages, chunks_indexed, user_id)
                )
            else:
                # Use old schema for backward compatibility
                cur.execute(
                    f"INSERT INTO documents (doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, user_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (doc_id, filename, pdf_path or "", vector_path or "", pages, chunks_indexed, user_id)
                )
            
            conn.commit()
            
            # Get the new document's ID
            cur.execute(f"SELECT id FROM documents WHERE doc_id = {placeholder}", (doc_id,))
            document = cur.fetchone()
            return document[0] if document else None
            
        finally:
            conn.close()
    
    def update_document_chunks_indexed(self, doc_id: str, chunks_indexed: int) -> bool:
        """Update the chunks_indexed count for a document"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            placeholder = self._get_placeholder()
            
            cur.execute(
                f"UPDATE documents SET chunks_indexed = {placeholder} WHERE doc_id = {placeholder}",
                (chunks_indexed, doc_id)
            )
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error updating document chunks count: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_document_by_doc_id(self, doc_id: str) -> Optional[Document]:
        """Get document by doc_id"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(f"""
                    SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    WHERE doc_id = {placeholder}
                """, (doc_id,))
                row = cur.fetchone()
                
                if row:
                    return Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
            else:
                # Use old schema for backward compatibility (SQLite/MySQL)
                cur.execute(f"""
                    SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    WHERE doc_id = {placeholder}
                """, (doc_id,))
                row = cur.fetchone()
                
                if row:
                    return Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
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
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(
                    f"SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at FROM documents WHERE user_id = {placeholder} ORDER BY created_at DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute(
                    f"SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at FROM documents WHERE user_id = {placeholder} ORDER BY created_at DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
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
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute("""
                    SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute("""
                    SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
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
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(f"""
                    SELECT d.id, d.doc_id, d.filename, d.file_id, d.pages, d.chunks_indexed, d.status, d.user_id, d.created_at, d.updated_at 
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
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute(f"""
                    SELECT d.id, d.doc_id, d.filename, d.pages, d.chunks_indexed, d.status, d.user_id, d.created_at, d.updated_at 
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
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
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
                if self.is_postgres:
                    # Check if email verification columns exist in PostgreSQL
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = 'userdata' 
                        AND column_name = 'is_verified'
                    """)
                    
                    column_exists = cur.fetchone()[0] > 0
                    
                    if not column_exists:
                        print("Adding email verification columns to userdata table (PostgreSQL)...")
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
                    # MySQL logic
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
    
    def _migrate_session_schema(self):
        """Migrate existing tables to support enhanced session management"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                if self.is_postgres:
                    # PostgreSQL migration logic
                    # Check if chat_sessions table exists
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_name = 'chat_sessions'
                    """)
                    
                    table_exists = cur.fetchone()[0] > 0
                    
                    if not table_exists:
                        print("Creating chat_sessions table (PostgreSQL)...")
                        # Table is already created in init_database for PostgreSQL
                        print("chat_sessions table already created in init_database")
                    
                    # Check if context columns exist in chathistory table
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = 'chathistory' 
                        AND column_name = 'context_type'
                    """)
                    
                    context_columns_exist = cur.fetchone()[0] > 0
                    
                    if not context_columns_exist:
                        print("Adding context columns to chathistory table (PostgreSQL)...")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_type VARCHAR(20) CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL'))")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_id VARCHAR(255)")
                        cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
                        conn.commit()
                        print("Context columns added to chathistory table successfully")
                else:
                    # MySQL migration logic
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.TABLES 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'chat_sessions'
                    """, (settings.DB_NAME,))
                    
                    table_exists = cur.fetchone()[0] > 0
                    
                    if not table_exists:
                        print("Creating chat_sessions table (MySQL)...")
                        cur.execute("""
                            CREATE TABLE chat_sessions(
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                session_id VARCHAR(255) UNIQUE NOT NULL,
                                user_id INT NOT NULL,
                                context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NOT NULL,
                                context_id VARCHAR(255) NULL,
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                                metadata JSON NULL,
                                FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE,
                                INDEX idx_user_context (user_id, context_type, context_id),
                                INDEX idx_session_id (session_id),
                                INDEX idx_last_activity (last_activity),
                                INDEX idx_active_sessions (user_id, is_active)
                            ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        """)
                        conn.commit()
                        print("chat_sessions table created successfully")
                    
                    # Check if context columns exist in chathistory table
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'chathistory' 
                        AND COLUMN_NAME = 'context_type'
                    """, (settings.DB_NAME,))
                    
                    context_columns_exist = cur.fetchone()[0] > 0
                    
                    if not context_columns_exist:
                        print("Adding context columns to chathistory table (MySQL)...")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NULL")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_id VARCHAR(255) NULL")
                        cur.execute("CREATE INDEX idx_chathistory_context ON chathistory (context_type, context_id)")
                        conn.commit()
                        print("Context columns added to chathistory table successfully")
                    
            else:
                # Check if chat_sessions table exists in SQLite
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'")
                table_exists = cur.fetchone() is not None
                
                if not table_exists:
                    print("Creating chat_sessions table (SQLite)...")
                    cur.execute("""
                        CREATE TABLE chat_sessions(
                            id INTEGER PRIMARY KEY,
                            session_id TEXT UNIQUE NOT NULL,
                            user_id INTEGER NOT NULL,
                            context_type TEXT NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                            context_id TEXT NULL,
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                            metadata TEXT NULL,
                            FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                        )
                    """)
                    
                    # Create indexes
                    cur.execute("CREATE INDEX idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
                    cur.execute("CREATE INDEX idx_chat_sessions_session_id ON chat_sessions (session_id)")
                    cur.execute("CREATE INDEX idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
                    cur.execute("CREATE INDEX idx_chat_sessions_active ON chat_sessions (user_id, is_active)")
                    
                    conn.commit()
                    print("chat_sessions table created successfully")
                
                # Check if context columns exist in chathistory table
                cur.execute("PRAGMA table_info(chathistory)")
                columns = [row[1] for row in cur.fetchall()]
                
                if 'context_type' not in columns:
                    print("Adding context columns to chathistory table (SQLite)...")
                    cur.execute("ALTER TABLE chathistory ADD COLUMN context_type TEXT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL') OR context_type IS NULL)")
                    cur.execute("ALTER TABLE chathistory ADD COLUMN context_id TEXT NULL")
                    cur.execute("CREATE INDEX idx_chathistory_context ON chathistory (context_type, context_id)")
                    conn.commit()
                    print("Context columns added to chathistory table successfully")
                    
        except Exception as e:
            print(f"Session schema migration error: {e}")
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

# Global database manager instance
db_manager = DatabaseManager()
