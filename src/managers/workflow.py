import os
import shutil
import json
import time
import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QTextEdit, 
    QFormLayout, QGridLayout, QTabWidget, QStackedWidget, QMessageBox, QFileDialog,
    QSplitter, QApplication, QInputDialog
)
from PySide6.QtCore import Qt, QUrl, QMimeData, QTimer
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor

from .base import BaseManagerWidget
import base64
from ..core import (
    SUPPORTED_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, 
    HAS_MARKDOWN, calculate_structure_path, PREVIEW_EXTENSIONS
)
from ..ui_components import SmartMediaWidget, ZoomWindow, TaskMonitorWidget
from ..ui.workflow_viewer import WorkflowGraphViewer
from .example import ExampleTabWidget
from ..workers import ImageLoader

try:
    import markdown
except ImportError:
    pass

class WorkflowManagerWidget(BaseManagerWidget):
    def __init__(self, directories, app_settings, task_monitor, parent_window=None):
        self.task_monitor = task_monitor
        self.parent_window = parent_window
        
        # Filter directories for 'workflow' mode
        wf_dirs = {k: v for k, v in directories.items() if v.get("mode") == "workflow"}
        super().__init__(wf_dirs, SUPPORTED_EXTENSIONS["workflow"], app_settings)

    def set_directories(self, directories):
        # Filter directories for 'workflow' mode
        wf_dirs = {k: v for k, v in directories.items() if v.get("mode") == "workflow"}
        super().set_directories(wf_dirs)
        if hasattr(self, 'tab_example'):
            self.tab_example.directories = directories

    # [Fix] Override mode
    def get_mode(self): return "workflow"

    def init_center_panel(self):

        # [Refactor] Use shared setup
        self._setup_info_panel()
        
        # Extended SmartMediaWidget for JSON Drag & Drop
        self.preview_lbl = WorkflowDraggableMediaWidget(loader=self.image_loader_thread, player_type="preview")
        self.preview_lbl.setMinimumSize(100, 100)
        self.preview_lbl.clicked.connect(self.on_preview_click)
        self.center_layout.addWidget(self.preview_lbl, 1)
        
        # Buttons
        # [Refactor] Use QGridLayout for 2x2 arrangement
        center_btn_layout = QGridLayout()
        
        # Row 0
        self.btn_copy = QPushButton("📋 Copy")
        self.btn_copy.setToolTip("Copy workflow JSON to clipboard (Paste in ComfyUI)")
        self.btn_copy.clicked.connect(self.copy_workflow_to_clipboard)
        center_btn_layout.addWidget(self.btn_copy, 0, 0)

        # Renamed from btn_replace to btn_change_thumb to avoid confusion
        self.btn_change_thumb = QPushButton("🖼️ Change Thumb")
        self.btn_change_thumb.setToolTip("Change the thumbnail image for the selected workflow")
        self.btn_change_thumb.clicked.connect(self.replace_thumbnail)
        center_btn_layout.addWidget(self.btn_change_thumb, 0, 1)
        
        # Row 1
        btn_open = QPushButton("📂 Open Folder")
        btn_open.setToolTip("Open the containing folder in File Explorer")
        btn_open.clicked.connect(self.open_current_folder)
        center_btn_layout.addWidget(btn_open, 1, 0)
        
        self.btn_replace_content = QPushButton("🔄 Replace")
        self.btn_replace_content.setToolTip("Replace current workflow content with another JSON file")
        self.btn_replace_content.clicked.connect(self.replace_workflow_content)
        center_btn_layout.addWidget(self.btn_replace_content, 1, 1)

        self.center_layout.addLayout(center_btn_layout)





    def init_right_panel(self):
        # Tabs (from Base)
        self.tabs = self.setup_content_tabs()
        
        # Tab: Graph Preview (First)
        self.graph_viewer = WorkflowGraphViewer()
        self.tabs.insertTab(0, self.graph_viewer, "Preview")
        self.tabs.setCurrentIndex(0)
        
        # Tab: Raw JSON
        self.tab_raw = QWidget()
        raw_layout = QVBoxLayout(self.tab_raw)
        self.txt_raw = QTextBrowser()
        raw_layout.addWidget(self.txt_raw)
        self.tabs.addTab(self.tab_raw, "Raw JSON")

        self.right_layout.addWidget(self.tabs)

    def on_tree_select(self):
        item = self.tree.currentItem()
        if not item: return
        
        # [Memory] Fast cleanup
        self.preview_lbl.clear_memory()
        if hasattr(self, 'tab_example'):
             self.tab_example.unload_current_examples()
             
        path = item.data(0, Qt.UserRole)
        type_ = item.data(0, Qt.UserRole + 1)
        
        if type_ == "file" and path:
            if not os.path.exists(path): return
            self.current_path = path
            self._load_details(path)
            

            
            # Pass the JSON path to the draggable widget so it knows what to drag
            self.preview_lbl.set_json_path(path)
            
    def closeEvent(self, event):
        if hasattr(self, 'preview_lbl'):
             self.preview_lbl.clear_memory()
        super().closeEvent(event)
    def _load_details(self, path):
        # [Refactor] Use shared logic from BaseManagerWidget
        filename, size_str, date_str, preview_path = self._load_common_file_details(path)
        
        self.info_labels["Name"].setText(filename)
        self.info_labels["Size"].setText(size_str)
        self.info_labels["Date"].setText(date_str)
        self.info_labels["Path"].setText(path)
        
        self.preview_lbl.set_media(preview_path)
        
        # Load Raw JSON
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
                self.txt_raw.setText(raw_text)
                
                # Load Graph Preview
                if hasattr(self, 'graph_viewer'):
                     try:
                         json_data = json.loads(raw_text)
                         self.graph_viewer.load_workflow(json_data)
                     except Exception as e:
                         self.graph_viewer.clear_graph()
        except Exception as e:
            self.txt_raw.setText(f"Error reading file: {e}")

        # Load Note (Standardized)
        self.load_content_data(path)







    def copy_workflow_to_clipboard(self):
        """Copies the content of the current JSON workflow file to the clipboard in ComfyUI compatible format (Nodes Only)."""
        if not hasattr(self, 'current_path') or not self.current_path or not os.path.exists(self.current_path):
            QMessageBox.warning(self, "Warning", "No workflow selected.")
            return

        try:
            with open(self.current_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 1. Validation & Extraction
            raw_json = json.loads(content)
            
            # [Fix] Detect if workflow data is wrapped (e.g. "workflow": { ... } or root)
            # Some exported files might wrap the graph in a "workflow" key (especially from API saves or specific tools)
            graph_data = raw_json
            if "nodes" not in raw_json and "workflow" in raw_json:
                 graph_data = raw_json["workflow"]


                 
            nodes = graph_data.get("nodes", [])
            links = graph_data.get("links", [])
            groups = graph_data.get("groups", [])
            config = graph_data.get("config", {})
            extra = graph_data.get("extra", {})
            version = graph_data.get("version", 0.4)
            
            # [Fix] Helper function to convert links (Array -> Dict)
            def convert_links(links_list):
                formatted = []
                for link in links_list:
                    # Standard Link: [id, origin_id, origin_slot, target_id, target_slot, type]
                    if isinstance(link, list):
                        if len(link) >= 5:
                            formatted.append({
                                "id": link[0],
                                "origin_id": link[1],
                                "origin_slot": link[2],
                                "target_id": link[3],
                                "target_slot": link[4],
                                "type": link[5] if len(link) > 5 else "*"
                            })
                        else:
                            # Too short, probably invalid or weird format. Keep as is.
                            formatted.append(link)
                    else:
                        # Already dict or unknown (keep as is)
                        formatted.append(link)
                return formatted

            # 1. Convert Main Links
            formatted_links = convert_links(links)
            
            # 2. valid subgraphs extraction (Ensure it's a list)
            # [Fix] Check both root 'subgraphs' and 'definitions.subgraphs' (Found in recent ComfyUI saves)
            subgraphs_data = graph_data.get("subgraphs", [])
            if not subgraphs_data:
                definitions = graph_data.get("definitions", {})
                if isinstance(definitions, dict):
                    subgraphs_data = definitions.get("subgraphs", [])
            
            if not isinstance(subgraphs_data, list): subgraphs_data = []

            # 3. Recursively Convert Links in Subgraphs
            # Subgraphs have their own 'links' array which must also be converted.
            formatted_subgraphs = []
            for sg in subgraphs_data:
                if isinstance(sg, dict):
                    # Deep copy to avoid mutating original if needed, but here we just replace 'links'
                    new_sg = sg.copy()
                    if "links" in new_sg:
                        new_sg["links"] = convert_links(new_sg["links"])
                    formatted_subgraphs.append(new_sg)
                else:
                    formatted_subgraphs.append(sg)

            # Debug Log
            self.task_monitor.log_message(f"Extracting: {len(nodes)} nodes, {len(formatted_links)} links, {len(formatted_subgraphs)} subgraphs")
            
            # Construct payload
            # [Fix] Strictly minimal payload for "Paste" support.
            # Removing 'config', 'extra', 'version' to prevent "Load Workflow" behavior or conflicts.
            # [Update] Added 'reroutes' and 'subgraphs' to match ComfyUI clipboard format exactly.
            payload = {
                "nodes": nodes,
                "links": formatted_links,
                "groups": groups,
                "reroutes": graph_data.get("reroutes", []),
                "subgraphs": formatted_subgraphs,
            }
            


            # 2. Prepare Data for ComfyUI (HTML + Base64)
            # [Fix] Removing separators to ensure standard spacing compatibility, though slightly larger.
            minified_json = json.dumps(payload) 
            encoded_bytes = base64.b64encode(minified_json.encode('utf-8'))
            encoded_str = encoded_bytes.decode('utf-8')
            
            # Use the exact HTML wrapper format akin to ComfyNodeBuilder
            html_data = (
                "<html><body>"
                "<!--StartFragment-->"
                f'<meta charset="utf-8"><div><span data-metadata="{encoded_str}"></span></div>'
                "<!--EndFragment-->"
                "</body></html>"
            )
            
            # 3. Set Clipboard with MimeData
            mime_data = QMimeData()
            mime_data.setText(minified_json) # Fallback to JSON text
            mime_data.setHtml(html_data) # For ComfyUI (HTML)
            
            clipboard = QApplication.clipboard()
            clipboard.setMimeData(mime_data)
            
            self.task_monitor.log_message(f"Copied to clipboard: {os.path.basename(self.current_path)}")
            
            # [Update] Use status bar message instead of popup
            msg = f"Workflow copied! ({len(nodes)} nodes, {len(links)} links) Paste in ComfyUI."
            self.show_status_message(msg, 3000)
            
        except json.JSONDecodeError:
             self.show_status_message("Error: Invalid JSON format.", 3000)
        except Exception as e:
            self.show_status_message(f"Error: {e}", 3000)

    def replace_workflow_content(self):
        """
        [New Feature] Replace the content of the currently selected workflow file 
        with the content of another JSON file selected by the user.
        """
        if not hasattr(self, 'current_path') or not self.current_path or not os.path.exists(self.current_path):
            QMessageBox.warning(self, "Warning", "No workflow selected.")
            return

        # 1. Select Source File
        source_path, _ = QFileDialog.getOpenFileName(
            self, "Select Replacement Workflow (JSON)", "", "Workflow Files (*.json);;All Files (*)"
        )
        
        if not source_path: return
        if os.path.abspath(source_path) == os.path.abspath(self.current_path):
            QMessageBox.information(self, "Info", "Source and target are the same file.")
            return

        # 2. Confirm Action
        reply = QMessageBox.question(
            self, "Confirm Replace", 
            f"Are you sure you want to replace the content of:\n{os.path.basename(self.current_path)}\n\nWith content from:\n{os.path.basename(source_path)}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply != QMessageBox.Yes: return

        try:
            # 3. Read Source Content
            with open(source_path, 'r', encoding='utf-8') as f_src:
                new_content = f_src.read()
                
            # Validate JSON
            json.loads(new_content)
            
            # 4. Write to Target
            with open(self.current_path, 'w', encoding='utf-8') as f_dst:
                f_dst.write(new_content)
                
            self.show_status_message(f"Replaced content with {os.path.basename(source_path)}", 3000)
            
            # 5. Refresh UI
            self._load_details(self.current_path)
            
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "Selected file is not valid JSON.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to replace content: {e}")


    # === Remove / Rename Feature ===

    def init_left_bottom(self, layout):
        """Override to add Remove/Rename buttons to the bottom of the left panel."""
        
        # Add 'Template Mode' checkbox
        from PySide6.QtWidgets import QCheckBox
        self.chk_show_workflow_only = QCheckBox("Template Mode")
        self.chk_show_workflow_only.setToolTip(
            "Filter the list to show exclusively valid ComfyUI workflow JSON files.\n"
            "Automatically hides any folders that do not contain workflows.\n"
            "This is useful for browsing a clean list of your workflow templates."
        )
        self.chk_show_workflow_only.stateChanged.connect(self._on_show_workflow_only_changed)
        layout.addWidget(self.chk_show_workflow_only)
        
        btn_layout = QHBoxLayout()
        
        btn_remove = QPushButton("🗑️ Remove")
        btn_remove.setToolTip("Permanently delete the selected workflow and its resources")
        btn_remove.clicked.connect(self.remove_workflow)
        
        btn_rename = QPushButton("✏️ Rename")
        btn_rename.setToolTip("Rename the selected workflow and its resources")
        btn_rename.clicked.connect(self.rename_workflow)
        
        btn_layout.addWidget(btn_remove)
        btn_layout.addWidget(btn_rename)
        layout.addLayout(btn_layout)

    def _on_show_workflow_only_changed(self, state):
        self.refresh_list()

    def get_scanner_filter_mode(self):
        """Override to pass filter mode to FileScannerWorker."""
        if hasattr(self, 'chk_show_workflow_only') and self.chk_show_workflow_only.isChecked():
            return "workflow_template"
        return None

    def remove_workflow(self):
        """
        Permanently deletes the selected workflow and its associated resources.
        Resources include:
        - The workflow file itself (.json)
        - Thumbnail/Preview files
        - Cache directory (notes, examples)
        """
        if not self.current_path or not os.path.exists(self.current_path):
            QMessageBox.warning(self, "Warning", "No workflow selected.")
            return

        filename = os.path.basename(self.current_path)
        
        # Confirm Delete
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to PERMANENTLY delete:\n{filename}\n\nThis will also delete:\n- Thumbnails/Previews\n- Notes & Metadata",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply != QMessageBox.Yes: return

        # 1. Unload resources
        if hasattr(self, 'preview_lbl'): 
            self.preview_lbl.clear_memory()
            self.preview_lbl.set_media(None)
        if hasattr(self, 'graph_viewer'):
            self.graph_viewer.clear_graph()
        if hasattr(self, 'tab_example'): 
            self.tab_example.unload_current_examples()
            
        # Ensure image loader isn't holding it
        if hasattr(self, 'image_loader_thread'):
            self.image_loader_thread.remove_from_cache(self.current_path)
            
        QApplication.processEvents()

        # [Refactor] Delegate to BaseManagerWidget's centralized method
        success, deleted_count, errors = self.remove_associated_files(self.current_path)
        
        if errors:
            msg = "Completed with errors:\n" + "\n".join(errors)
            QMessageBox.warning(self, "Delete Incomplete", msg)
        else:
            self.show_status_message(f"Deleted {deleted_count} items.")
            
        self.current_path = None
        self.refresh_list()

    def rename_workflow(self):
        """
        Renames the selected workflow and its associated resources.
        """
        if not self.current_path or not os.path.exists(self.current_path):
            QMessageBox.warning(self, "Warning", "No workflow selected.")
            return

        old_filename = os.path.basename(self.current_path)
        old_base = os.path.splitext(old_filename)[0]
        ext = os.path.splitext(old_filename)[1]
        
        # 1. Get New Name
        new_base, ok = QInputDialog.getText(self, "Rename Workflow", "New Name:", text=old_base)
        if not ok or not new_base: return
        
        # 2. Unload resources
        if hasattr(self, 'preview_lbl'): 
            self.preview_lbl.clear_memory()
            self.preview_lbl.set_media(None)
        if hasattr(self, 'graph_viewer'):
            self.graph_viewer.clear_graph()
        if hasattr(self, 'tab_example'): 
            self.tab_example.unload_current_examples()
            
        QApplication.processEvents()

        # [Refactor] Delegate to BaseManagerWidget's centralized method
        success, renamed_count, errors = self.rename_associated_files(self.current_path, new_base)

        if not success and errors and "A file with that name" in errors[0]:
            QMessageBox.warning(self, "Error", errors[0])
            return
        elif not success and errors and "Invalid characters" in errors[0]:
            QMessageBox.warning(self, "Invalid Name", errors[0])
            return

        if errors:
            msg = "Completed with errors:\n" + "\n".join(errors)
            QMessageBox.warning(self, "Rename Incomplete", msg)
        else:
            self.show_status_message(f"Renamed {renamed_count} files/dirs.")
        
        self.current_path = None
        self.refresh_list()


class WorkflowDraggableMediaWidget(SmartMediaWidget):
    """
    Subclass of SmartMediaWidget that drags the JSON file path instead of the image.
    """
    def set_json_path(self, path):
        self.json_path = path

    def mouseMoveEvent(self, event):
        if not self._drag_start_pos: return
        if not (event.buttons() & Qt.LeftButton): return
        current_pos = event.position().toPoint()
        if (current_pos - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        
        # Ensure we have a JSON path to drag
        if hasattr(self, 'json_path') and self.json_path and os.path.exists(self.json_path):
            drag = QDrag(self)
            mime_data = QMimeData()
            # This is the standard way to drag files in OS
            mime_data.setUrls([QUrl.fromLocalFile(self.json_path)])
            drag.setMimeData(mime_data)
            
            # Create default drag pixmap for JSON
            pix = QPixmap(100, 100)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setBrush(QColor(60, 60, 60))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, 100, 100, 10, 10)
            painter.setPen(QColor(255, 255, 255))
            # Use App font (QSS styled)
            font = QApplication.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pix.rect(), Qt.AlignCenter, "JSON\nWorkflow")
            painter.end()
            drag.setPixmap(pix)
            drag.setHotSpot(pix.rect().center())
            
            drag.exec(Qt.CopyAction)
            self._drag_start_pos = None
        else:
            # Fallback to default behavior if no JSON path (though usually we want JSON for workflow mode)
            super().mouseMoveEvent(event)

