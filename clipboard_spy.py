import sys
import json
import base64
from PySide6.QtWidgets import QApplication

def on_clipboard_change():
    clipboard = QApplication.clipboard()
    mime_data = clipboard.mimeData()
    
    print("\n[!] Clipboard changed detected!")
    
    is_comfyui = False
    
    if mime_data.hasHtml():
        html = mime_data.html()
        
        # Extract ComfyUI special HTML payload
        if 'data-metadata="' in html:
            is_comfyui = True
            print(" -> ComfyUI HTML format found! Extracting metadata...")
            try:
                start = html.find('data-metadata="') + len('data-metadata="')
                end = html.find('"', start)
                b64_data = html[start:end]
                
                json_str = base64.b64decode(b64_data).decode('utf-8')
                data = json.loads(json_str)
                
                with open("comfyui_clipboard_dump.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    
                print(f" -> Successfully dumped to 'comfyui_clipboard_dump.json'!")
                print(f" -> Nodes: {len(data.get('nodes', []))}, Links: {len(data.get('links', []))}")
            except Exception as e:
                print(f" -> [ERROR] Failed to parse ComfyUI data: {e}")
                
    if mime_data.hasText() and not is_comfyui:
        text = mime_data.text()
        if text.strip().startswith("{") and "nodes" in text:
             print(" -> ComfyUI RAW JSON Text format found!")
             try:
                 data = json.loads(text)
                 with open("comfyui_clipboard_dump.json", "w", encoding="utf-8") as f:
                     json.dump(data, f, indent=4, ensure_ascii=False)
                 print(f" -> Successfully dumped to 'comfyui_clipboard_dump.json'!")
                 print(f" -> Nodes: {len(data.get('nodes', []))}, Links: {len(data.get('links', []))}")
             except Exception as e:
                     print(f" -> [ERROR] Failed to parse JSON text: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    clipboard = app.clipboard()
    clipboard.dataChanged.connect(on_clipboard_change)
    print("======================================================")
    print("ComfyUI Clipboard Spy is running...")
    print("Please go to ComfyUI, select nodes WITH links, and COPY (Ctrl+C).")
    print("======================================================")
    sys.exit(app.exec())
