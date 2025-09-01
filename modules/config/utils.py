"""
Utility functions for the Floor Plan Agent API
"""
import os
import json
import time
import threading
from typing import Dict, Any
from modules.config.settings import settings

def delete_file(path: str):
    """Delete file with error handling"""
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"DEBUG: Deleted file: {path}")
    except Exception as e:
        print(f"Error deleting file {path}: {e}")

def delete_file_after_delay(path: str, delay_seconds: int):
    """Delete file after specified delay in seconds"""
    def delayed_delete():
        time.sleep(delay_seconds)
        delete_file(path)
    
    thread = threading.Thread(target=delayed_delete)
    thread.daemon = True
    thread.start()

def load_registry() -> Dict[str, Any]:
    """Load document registry from JSON file"""
    registry_path = os.path.join(settings.DATA_DIR, "registry.json")
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_registry(reg: Dict[str, Any]):
    """Save document registry to JSON file"""
    registry_path = os.path.join(settings.DATA_DIR, "registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)

def validate_file_path(file_path: str, allowed_base_dir: str = None) -> bool:
    """Validate file path for security"""
    if allowed_base_dir is None:
        allowed_base_dir = settings.DATA_DIR
    
    abs_path = os.path.abspath(file_path)
    return abs_path.startswith(allowed_base_dir) and os.path.exists(abs_path)

def generate_unique_filename(base_name: str, extension: str, directory: str) -> str:
    """Generate a unique filename in the specified directory"""
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    return os.path.join(directory, f"{base_name}_{unique_id}.{extension}")