"""
Configuration settings for the Floor Plan Agent API
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    """Application settings"""
    
    # API Configuration
    APP_NAME = "Floorplan LangGraph Agent + RAG API"
    VERSION = "1.0.0"
    HOST = "0.0.0.0"
    PORT = 8000
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    
    # Email Configuration for verification
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@esticore.com')
    
    # Email verification settings
    VERIFICATION_TOKEN_EXPIRE_HOURS = int(os.getenv('VERIFICATION_TOKEN_EXPIRE_HOURS', 1))
    OTP_EXPIRE_MINUTES = int(os.getenv('OTP_EXPIRE_MINUTES', 5))
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
    
    # LangSmith Configuration
    LANGSMITH_TRACING = os.getenv('LANGSMITH_TRACING', 'false').lower() == 'true'
    LANGSMITH_ENDPOINT = os.getenv('LANGSMITH_ENDPOINT')
    LANGSMITH_API_KEY = os.getenv('LANGSMITH_API_KEY')
    LANGSMITH_PROJECT = os.getenv('LANGSMITH_PROJECT')
    
    # Roboflow Configuration
    ROBOFLOW_API_URL = "https://serverless.roboflow.com"
    ROBOFLOW_API_KEY = "vVIEhzGbQzi4RDzrfvgd"
    ROBOFLOW_MODEL_ID = "esticore-floorplan-68jz3/3"
    
    # Tavily Configuration
    TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
    
    # Database Configuration
    DATABASE_NAME = "project.db"  # Legacy SQLite database
    
    # Database Connection Configuration
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = int(os.getenv('DB_PORT', 5432))  # Default to PostgreSQL port
    DB_NAME = os.getenv('DB_NAME')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    
    # Database type selection and validation
    USE_RDS = bool(DB_HOST and DB_NAME and DB_USER and DB_PASSWORD)
    IS_POSTGRES = DB_PORT == 5432
    IS_MYSQL = DB_PORT == 3306
    
    # PostgreSQL/pgvector Configuration
    PGVECTOR_ENABLED = os.getenv('PGVECTOR_ENABLED', 'true').lower() == 'true'
    VECTOR_DIMENSIONS = int(os.getenv('VECTOR_DIMENSIONS', 1536))  # OpenAI embedding dimensions
    VECTOR_INDEX_LISTS = int(os.getenv('VECTOR_INDEX_LISTS', 100))  # IVFFlat index parameter
    
    # Database Connection Pool Settings
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 10))
    DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', 20))
    DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', 30))
    DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', 3600))  # 1 hour
    
    # Database Storage Configuration
    USE_DATABASE_STORAGE = USE_RDS and IS_POSTGRES and PGVECTOR_ENABLED
    USE_LOCAL_STORAGE = not USE_DATABASE_STORAGE
    
    # Directory Configuration
    # Use environment variable for DATA_DIR if available, otherwise use relative path
    DATA_DIR = os.getenv('DATA_DIR', os.path.abspath("data"))
    
    # Configure directories based on storage type
    if USE_DATABASE_STORAGE:
        # PostgreSQL database storage - minimal local directories
        VECTORS_DIR = None  # Not used with pgvector
        OUTPUT_DIR = None   # Not used with database storage
        DOCS_DIR = None     # Not used with database storage
        IMAGES_DIR = os.path.join(DATA_DIR, "images")  # Still needed for temporary image processing
        
        print("INFO: Using PostgreSQL database storage - local file directories disabled")
    else:
        # Local file storage (SQLite or MySQL without pgvector)
        VECTORS_DIR = os.path.join(DATA_DIR, "vectors")
        OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
        DOCS_DIR = os.path.join(DATA_DIR, "docs")
        IMAGES_DIR = os.path.join(DATA_DIR, "images")
        
        print("INFO: Using local file storage - all directories enabled")
    
    # Security Configuration
    PASSWORD_MIN_LENGTH = 8
    
    # Agent Configuration
    RECURSION_LIMIT = 25
    CHAT_RECURSION_LIMIT = 20
    CHAT_HISTORY_LIMIT = 20
    SESSION_CLEANUP_HOURS = 24
    
    # Enhanced Session Management Configuration
    SESSION_CACHE_MAX_SIZE = int(os.getenv('SESSION_CACHE_MAX_SIZE', 1000))
    SESSION_MAINTENANCE_INTERVAL = int(os.getenv('SESSION_MAINTENANCE_INTERVAL', 3600))  # 1 hour
    SESSION_ACTIVITY_UPDATE_PROBABILITY = float(os.getenv('SESSION_ACTIVITY_UPDATE_PROBABILITY', 0.01))  # 1%
    SESSION_CLEANUP_PROBABILITY = float(os.getenv('SESSION_CLEANUP_PROBABILITY', 0.01))  # 1%
    
    # Context Validation Settings
    ENABLE_STRICT_CONTEXT_VALIDATION = os.getenv('ENABLE_STRICT_CONTEXT_VALIDATION', 'true').lower() == 'true'
    ALLOW_CONTEXT_SWITCHING = os.getenv('ALLOW_CONTEXT_SWITCHING', 'true').lower() == 'true'
    
    # Session Security Settings
    SESSION_ACCESS_VALIDATION_ENABLED = os.getenv('SESSION_ACCESS_VALIDATION_ENABLED', 'true').lower() == 'true'
    SESSION_EXPIRY_GRACE_PERIOD_HOURS = int(os.getenv('SESSION_EXPIRY_GRACE_PERIOD_HOURS', 1))
    
    # File Configuration
    FILE_DELETE_DELAY = 3600  # 1 hour
    CHAT_FILE_DELETE_DELAY = 7200  # 2 hours
    
    # Database Migration Configuration
    MIGRATION_BATCH_SIZE = int(os.getenv('MIGRATION_BATCH_SIZE', 100))  # Files per batch
    MIGRATION_PROGRESS_INTERVAL = int(os.getenv('MIGRATION_PROGRESS_INTERVAL', 10))  # Log every N files
    ENABLE_MIGRATION_ROLLBACK = os.getenv('ENABLE_MIGRATION_ROLLBACK', 'true').lower() == 'true'
    
    # Database Maintenance Configuration
    AUTO_VACUUM_ENABLED = os.getenv('AUTO_VACUUM_ENABLED', 'true').lower() == 'true'
    VACUUM_SCHEDULE_HOURS = int(os.getenv('VACUUM_SCHEDULE_HOURS', 24))  # Run vacuum every 24 hours
    CLEANUP_ORPHANED_RECORDS = os.getenv('CLEANUP_ORPHANED_RECORDS', 'true').lower() == 'true'
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 100))  # Maximum file size for database storage
    
    # Performance Configuration
    ENABLE_QUERY_LOGGING = os.getenv('ENABLE_QUERY_LOGGING', 'false').lower() == 'true'
    SLOW_QUERY_THRESHOLD_MS = int(os.getenv('SLOW_QUERY_THRESHOLD_MS', 1000))  # Log queries slower than 1s
    ENABLE_CONNECTION_POOLING = os.getenv('ENABLE_CONNECTION_POOLING', 'true').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate required settings"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Validate database configuration
        if cls.USE_RDS:
            if not all([cls.DB_HOST, cls.DB_NAME, cls.DB_USER, cls.DB_PASSWORD]):
                raise ValueError("Database configuration incomplete. Please set DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD")
            
            # Validate database type
            if cls.IS_POSTGRES:
                print(f"✓ Using PostgreSQL database: {cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")
                if cls.PGVECTOR_ENABLED:
                    print(f"✓ pgvector enabled with {cls.VECTOR_DIMENSIONS} dimensions")
                    print(f"✓ Database storage enabled - files and vectors stored in PostgreSQL")
                else:
                    print("⚠ pgvector disabled - using local file storage")
            elif cls.IS_MYSQL:
                print(f"✓ Using MySQL database: {cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")
                print("ℹ MySQL detected - using local file storage (pgvector not available)")
            else:
                print(f"⚠ Unknown database type on port {cls.DB_PORT} - assuming local file storage")
            
            # Validate connection pool settings
            if cls.DB_POOL_SIZE < 1:
                raise ValueError("DB_POOL_SIZE must be at least 1")
            if cls.DB_POOL_TIMEOUT < 1:
                raise ValueError("DB_POOL_TIMEOUT must be at least 1 second")
                
        else:
            print("ℹ Using SQLite database with local file storage")
        
        # Validate vector configuration
        if cls.USE_DATABASE_STORAGE:
            if cls.VECTOR_DIMENSIONS not in [1536, 1024, 768, 512]:
                print(f"⚠ Unusual vector dimensions: {cls.VECTOR_DIMENSIONS} (common: 1536 for OpenAI)")
            if cls.VECTOR_INDEX_LISTS < 1:
                raise ValueError("VECTOR_INDEX_LISTS must be at least 1")
        
        # Log important environment information for debugging
        print("DEBUG: Environment information:")
        print(f"  Current working directory: {os.getcwd()}")
        print(f"  DATA_DIR environment variable: {os.getenv('DATA_DIR', 'Not set')}")
        print(f"  Script location: {os.path.abspath(__file__)}")
        
        # Create directories if they don't exist and log their paths
        directories = {'DATA_DIR': cls.DATA_DIR}
        
        # Add directories based on storage configuration
        if cls.USE_DATABASE_STORAGE:
            # Only need images directory for temporary processing
            directories['IMAGES_DIR'] = cls.IMAGES_DIR
        else:
            # Need all directories for local file storage
            directories.update({
                'VECTORS_DIR': cls.VECTORS_DIR,
                'OUTPUT_DIR': cls.OUTPUT_DIR,
                'DOCS_DIR': cls.DOCS_DIR,
                'IMAGES_DIR': cls.IMAGES_DIR
            })
        
        print("DEBUG: Directory configuration:")
        for name, directory in directories.items():
            if directory:  # Only create directories that are defined
                os.makedirs(directory, exist_ok=True)
                print(f"  ✓ {name}: {directory}")
                print(f"    exists: {os.path.exists(directory)}")
                print(f"    writable: {os.access(directory, os.W_OK)}")
            else:
                print(f"  - {name}: Disabled (using database storage)")
        
        # Log storage configuration summary
        print("\nStorage Configuration Summary:")
        print(f"  Database Storage: {'✓ Enabled' if cls.USE_DATABASE_STORAGE else '✗ Disabled'}")
        print(f"  Local File Storage: {'✓ Enabled' if cls.USE_LOCAL_STORAGE else '✗ Disabled'}")
        print(f"  Vector Storage: {'PostgreSQL/pgvector' if cls.USE_DATABASE_STORAGE else 'Local FAISS files'}")
        print(f"  File Storage: {'PostgreSQL binary' if cls.USE_DATABASE_STORAGE else 'Local filesystem'}")

# Global settings instance
settings = Settings()