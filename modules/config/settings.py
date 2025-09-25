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
    ROBOFLOW_MODEL_ID = "full-set-menu/5"
    
    # Database Configuration
    DATABASE_NAME = "project.db"  # Legacy SQLite database
    
    # AWS RDS MySQL Configuration
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_NAME = os.getenv('DB_NAME')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    
    # Database type selection
    USE_RDS = bool(DB_HOST and DB_NAME and DB_USER and DB_PASSWORD)
    
    # Directory Configuration
    # Use environment variable for DATA_DIR if available, otherwise use relative path
    DATA_DIR = os.getenv('DATA_DIR', os.path.abspath("data"))
    VECTORS_DIR = os.path.join(DATA_DIR, "vectors")
    OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
    DOCS_DIR = os.path.join(DATA_DIR, "docs")
    IMAGES_DIR = os.path.join(DATA_DIR, "images")
    
    # Security Configuration
    PASSWORD_MIN_LENGTH = 8
    
    # Agent Configuration
    RECURSION_LIMIT = 25
    CHAT_RECURSION_LIMIT = 20
    CHAT_HISTORY_LIMIT = 20
    SESSION_CLEANUP_HOURS = 24
    
    # File Configuration
    FILE_DELETE_DELAY = 3600  # 1 hour
    CHAT_FILE_DELETE_DELAY = 7200  # 2 hours
    
    @classmethod
    def validate(cls):
        """Validate required settings"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Validate database configuration
        if cls.USE_RDS:
            if not all([cls.DB_HOST, cls.DB_NAME, cls.DB_USER, cls.DB_PASSWORD]):
                raise ValueError("AWS RDS configuration incomplete. Please set DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD")
        
        # Log important environment information for debugging
        print("DEBUG: Environment information:")
        print(f"  Current working directory: {os.getcwd()}")
        print(f"  DATA_DIR environment variable: {os.getenv('DATA_DIR', 'Not set')}")
        print(f"  Script location: {os.path.abspath(__file__)}")
        
        # Create directories if they don't exist and log their paths
        directories = {
            'DATA_DIR': cls.DATA_DIR,
            'VECTORS_DIR': cls.VECTORS_DIR,
            'OUTPUT_DIR': cls.OUTPUT_DIR,
            'DOCS_DIR': cls.DOCS_DIR,
            'IMAGES_DIR': cls.IMAGES_DIR
        }
        
        print("DEBUG: Directory configuration:")
        for name, directory in directories.items():
            os.makedirs(directory, exist_ok=True)
            print(f"  {name}: {directory}")
            print(f"    exists: {os.path.exists(directory)}")
            print(f"    writable: {os.access(directory, os.W_OK)}")

# Global settings instance
settings = Settings()