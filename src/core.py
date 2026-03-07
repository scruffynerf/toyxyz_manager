import sys
import os
import json as std_json
import gzip
import re
import logging
from typing import Dict, Any, Optional

try:
    import orjson as json
except ImportError:
    import json as json

from PySide6.QtCore import QMutex

# ==========================================
# Feature Flags & Imports
# ==========================================
MISSING_DEPENDENCIES = []

try:
    import requests
except ImportError:
    MISSING_DEPENDENCIES.append("requests")

HAS_PILLOW = False
try:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    HAS_PILLOW = True
except ImportError:
    logging.warning("Pillow library is missing. pip install pillow")
    MISSING_DEPENDENCIES.append("pillow")

HAS_MARKDOWN = False
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    pass

HAS_MARKDOWNIFY = False
try:
    import markdownify
    HAS_MARKDOWNIFY = True
except ImportError:
    pass

# ==========================================
# Constants & Paths
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "manager_config.json")
CACHE_DIR_NAME = os.path.join(BASE_DIR, "cache")

# Extension Definitions
EXT_MODEL = {".ckpt", ".pt", ".bin", ".safetensors", ".gguf", ".pth"}
EXT_WORKFLOW = {".json"}
EXT_PROMPT = {".txt", ".json"} 

# Mode Mapping
SUPPORTED_EXTENSIONS = {
    "model": EXT_MODEL,
    "workflow": EXT_WORKFLOW,
    "prompt": EXT_PROMPT
}

PREVIEW_EXTENSIONS = [".mp4", ".webm", ".preview.png", ".png", ".jpg", ".jpeg", ".webp"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".preview.png"}
MAX_FILE_LOAD_MB = 200
MAX_FILE_LOAD_BYTES = MAX_FILE_LOAD_MB * 1024 * 1024

VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"} 

# ==========================================
# Helper Classes
# ==========================================
class QMutexWithLocker:
    def __init__(self, mutex: QMutex):
        self.mutex = mutex
    def __enter__(self):
        self.mutex.lock()
    def __exit__(self, exc_type, exc_value, traceback):
        self.mutex.unlock()

# ==========================================
# Utility Functions
# ==========================================
def sanitize_filename(filename: str) -> str:
    """Removes invalid characters from a filename."""
    return re.sub(r'[<>:\"/\\|?*]', '', filename).strip()

def calculate_structure_path(model_path: str, cache_root: str, directories: Dict[str, Any], mode: str = "model") -> str:
    """
    Calculates the structured cache path.
    New Strategy: Hierarchical structure based on base directory aliases and relative paths.
    Path: cache_root/<mode>/<Alias>/<Relative_Path>/<model_name>
    """
    model_name = os.path.splitext(os.path.basename(model_path))[0]
    
    safe_mode = sanitize_filename(mode)
    if not safe_mode: safe_mode = "model"
    
    model_path_norm = os.path.normpath(model_path)
    
    relative_structure = ""
    matched_alias = None
    
    for alias, data in directories.items():
        base_path = data.get("path") if isinstance(data, dict) else data
        base_path_norm = os.path.normpath(base_path)
        
        try:
            rel = os.path.relpath(model_path_norm, base_path_norm)
            if not rel.startswith("..") and not os.path.isabs(rel):
                matched_alias = sanitize_filename(alias)
                dirname = os.path.dirname(rel)
                if dirname:
                    relative_structure = os.path.join(matched_alias, dirname)
                else:
                    relative_structure = matched_alias
                break
        except ValueError:
            # handle cross-drive issues on Windows
            pass
            
    if not matched_alias:
        import hashlib
        hash_suffix = hashlib.md5(model_path_norm.encode('utf-8')).hexdigest()[:8]
        relative_structure = f"_external_{hash_suffix}"
        
    return os.path.join(cache_root, safe_mode, relative_structure, model_name)

# ==========================================
# Config Management
# ==========================================
def load_config(config_path=CONFIG_FILE) -> Dict[str, Any]:
    """Loads the configuration from JSON file and handles migration."""
    data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = std_json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            return {}

    settings = data.get("__settings__", {})
    directories = settings.get("directories", {})
    
    migrated = False
    new_directories = {}
    
    for alias, val in directories.items():
        if isinstance(val, str):
            new_directories[alias] = {"path": val, "mode": "model"}
            migrated = True
        else:
            new_directories[alias] = val
            
    if migrated:
        settings["directories"] = new_directories
        data["__settings__"] = settings
        save_config(data, config_path)
        logging.info("Config migrated to new structure.")
        
    return data

def save_config(data: Dict[str, Any], config_path=CONFIG_FILE):
    """Saves the configuration dict to JSON file."""
    try:
        with open(config_path, "w", encoding='utf-8') as f:
            std_json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Failed to save config: {e}")
        raise e

# ==========================================
# Metadata Imports (Refactored)
# ==========================================
from .metadata import (
    validate_metadata_type as validate_comfy_metadata,
    standardize_metadata
)
from .metadata.novelai import extract_novelai_data
from .metadata.comfy import parse_comfy_workflow
