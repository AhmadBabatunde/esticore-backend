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
    DATABASE_NAME = "project.db"
    
    # Directory Configuration
    DATA_DIR = os.path.abspath("data")
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
        
        # Create directories if they don't exist
        for directory in [cls.DATA_DIR, cls.VECTORS_DIR, cls.OUTPUT_DIR, cls.DOCS_DIR, cls.IMAGES_DIR]:
            os.makedirs(directory, exist_ok=True)

# Global settings instance
settings = Settings()