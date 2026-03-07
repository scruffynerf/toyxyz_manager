import sys
import os

# Add main project dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from PIL import Image
from src.metadata import validate_metadata_type, standardize_metadata

def test_filter():
    found = False
    for root, dirs, files in os.walk(r"c:\Users\toyxy\antigravity_pj\toyxyz_manager\.cache"):
        for f in files:
            if f.endswith(".png") or f.endswith(".jpg") or f.endswith(".webp"):
                img_path = os.path.join(root, f)
                try:
                    with Image.open(img_path) as img:
                        meta = standardize_metadata(img)
                        if meta["type"] != "unknown":
                            print(f"File: {img_path}")
                            print(f"Type: {meta['type']}")
                            print(f"Model: {str(meta.get('model', {})).lower()}")
                            print(f"Main: {str(meta.get('main', {})).lower()}")
                            found = True
                            return
                except Exception as e:
                    print(f"Error on {img_path}: {e}")
    if not found:
        print("No valid metadata images found in cache.")
                    
test_filter()
