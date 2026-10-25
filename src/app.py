"""
DIALux IFC Bridge - Main Desktop Application
Built with CustomTkinter and TkinterDnD2 for high-DPI modern Windows experience.
"""
import os
import sys
import threading
from typing import Optional, List, Dict
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

from .utils import (
    logger,
    get_default_export_dir,
    UNIT_TO_METERS,
    sanitize_filename
)
from .ifc_parser import IfcModelInspector, RELEVANT_CLASSES
from .obj_exporter import DialuxObjExporter
from .dxf_exporter import DialuxDxfExporter
from .dialux_bridge import (
    find_dialux_executable,
    get_dialux_windows,
    send_to_dialux,
    reveal_in_explorer
)

# Appearance setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class DialuxIFCApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        
        # Window configuration
        self.title("DIALux IFC Bridge — Free IFC Importer for DIALux evo")
        self.geometry("980x780")
        self.minsize(860, 680)
        
        # State variables
        self.current_ifc_path: Optional[str] = None
        self.inspector: Optional[IfcModelInspector] = None
        self.last_exported_obj: Optional[str] = None
        self.is_processing = False
        
        # Category checkboxes dict
        self.category_vars: Dict[str, ctk.BooleanVar] = {}
        # Storey checkboxes dict
        self.storey_vars: Dict[str, ctk.BooleanVar] = {}
        
        # UI Setup
        self._build_ui()
        self._check_dialux_status()
        self._setup_dnd()

    def _build_ui(self):
        """Build the responsive layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Main scrollable content
        
        # 1. Header Banner
        self._build_header()
        
        # 2. Hero Drop Zone
        self._build_drop_zone()
        
        # 3. Main Content Area (Two Columns: Model Info & Export Controls)
        self.content_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="transparent")
        self.content_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=5)
        self.content_frame.grid_columnconfigure(1, weight=4)
        self.content_frame.grid_rowconfigure(0, weight=1)
        
        # Left Panel: BIM Model Details
        self._build_model_panel(self.content_frame)
        
        # Right Panel: Conversion & Send to DIALux
        self._build_action_panel(self.content_frame)
        
        # 4. Progress & Status Footer
        self._build_footer()

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "#181b20"), height=65)
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)
        
        # Icon / Logo
        logo_label = ctk.CTkLabel(
            header_frame,
            text="⚡ DIALux IFC Bridge",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        logo_label.grid(row=0, column=0, padx=(20, 10), pady=12, sticky="w")
        
        sub_label = ctk.CTkLabel(
            header_frame,
            text="Free IFC & Revit BIM Import for DIALux evo",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        sub_label.grid(row=0, column=1, padx=0, pady=12, sticky="w")
        
        # DIALux Status Badge
        self.dialux_status_label = ctk.CTkLabel(
            header_frame,
            text="Checking DIALux...",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2b313a",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.dialux_status_label.grid(row=0, column=2, padx=20, pady=12, sticky="e")

    def _build_drop_zone(self):
        self.drop_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            border_width=2,
            border_color=("#3b8ed0", "#1f6aa5"),
            fg_color=("gray90", "#1e2229"),
            height=120
        )
        self.drop_frame.grid(row=1, column=0, padx=20, pady=(15, 12), sticky="ew")
        self.drop_frame.grid_columnconfigure(0, weight=1)
        
        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="📁  Drag & Drop your .IFC file here\n— or click to Browse —",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray20", "gray85")
        )
        self.drop_label.grid(row=0, column=0, pady=(18, 6))
        
        self.drop_sublabel = ctk.CTkLabel(
            self.drop_frame,
            text="Supports Revit, ArchiCAD, Tekla, BlenderBIM & all standard IFC2X3 / IFC4 models",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.drop_sublabel.grid(row=1, column=0, pady=(0, 16))
        
        # Click to browse
        self.drop_frame.bind("<Button-1>", lambda e: self._browse_file())
        self.drop_label.bind("<Button-1>", lambda e: self._browse_file())
        self.drop_sublabel.bind("<Button-1>", lambda e: self._browse_file())

    def _build_model_panel(self, parent):
        self.model_panel = ctk.CTkScrollableFrame(
            parent,
            label_text="BIM Model Inspection",
            label_font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        self.model_panel.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.model_panel.grid_columnconfigure(0, weight=1)
        
        # Placeholder before file is loaded
        self.placeholder_label = ctk.CTkLabel(
            self.model_panel,
            text="No IFC file loaded.\nDrop a file above to inspect building storeys,\nelements, and geometry.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            pady=40
        )
        self.placeholder_label.pack(fill="x", expand=True)

    def _build_action_panel(self, parent):
        self.action_panel = ctk.CTkFrame(parent, corner_radius=10)
        self.action_panel.grid(row=0, column=1, sticky="nsew")
        self.action_panel.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(
            self.action_panel,
            text="Export & Transfer Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title.pack(anchor="w", padx=16, pady=(14, 10))
        
        # Unit Override Options
        unit_frame = ctk.CTkFrame(self.action_panel, fg_color="transparent")
        unit_frame.pack(fill="x", padx=16, pady=4)
        
        ctk.CTkLabel(unit_frame, text="Unit Scale:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.unit_combo = ctk.CTkComboBox(
            unit_frame,
            values=["Automatic (from IFC)", "Meters (1.0)", "Millimeters (1/1000)", "Feet (0.3048)", "Inches (0.0254)"],
            width=180,
            command=self._on_unit_change
        )
        self.unit_combo.set("Automatic (from IFC)")
        self.unit_combo.pack(side="right")
        
        # Grouping Mode
        group_frame = ctk.CTkFrame(self.action_panel, fg_color="transparent")
        group_frame.pack(fill="x", padx=16, pady=4)
        
        ctk.CTkLabel(group_frame, text="Hierarchy Grouping:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.group_combo = ctk.CTkComboBox(
            group_frame,
            values=["By Storey & Category", "By Category Only", "Both"],
            width=180
        )
        self.group_combo.set("By Storey & Category")
        self.group_combo.pack(side="right")
        
        # Separator
        sep = ctk.CTkFrame(self.action_panel, height=2, fg_color=("gray75", "gray30"))
        sep.pack(fill="x", padx=16, pady=12)
        
        # BIG HERO BUTTON: Send to DIALux
        self.btn_send = ctk.CTkButton(
            self.action_panel,
            text="🚀  Send to DIALux evo",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=46,
            fg_color="#107c41",
            hover_color="#0e6b37",
            command=self._on_send_to_dialux
        )
        self.btn_send.pack(fill="x", padx=16, pady=(4, 8))
        
        send_info = ctk.CTkLabel(
            self.action_panel,
            text="Auto-converts, copies to clipboard (CF_HDROP),\nand activates DIALux evo directly.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="center"
        )
        send_info.pack(padx=16, pady=(0, 10))
        
        # Secondary Action Buttons
        self.btn_export_obj = ctk.CTkButton(
            self.action_panel,
            text="💾  Export OBJ / MTL As...",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=("#3a3f47", "#2e3440"),
            hover_color=("#4c535f", "#3b4252"),
            command=self._on_export_obj_custom
        )
        self.btn_export_obj.pack(fill="x", padx=16, pady=4)
        
        self.btn_export_dxf = ctk.CTkButton(
            self.action_panel,
            text="📐  Export 3D DXF CAD Underlay",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=("#3a3f47", "#2e3440"),
            hover_color=("#4c535f", "#3b4252"),
            command=self._on_export_dxf
        )
        self.btn_export_dxf.pack(fill="x", padx=16, pady=4)
        
        self.btn_open_folder = ctk.CTkButton(
            self.action_panel,
            text="📁  Open Output Folder",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color="gray",
            command=self._on_open_folder
        )
        self.btn_open_folder.pack(fill="x", padx=16, pady=(4, 16))

    def _build_footer(self):
        footer_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray85", "#181b20"), height=45)
        footer_frame.grid(row=3, column=0, sticky="ew", padx=0, pady=0)
        footer_frame.grid_columnconfigure(0, weight=1)
        
        self.progress_bar = ctk.CTkProgressBar(footer_frame, height=4)
        self.progress_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(
            footer_frame,
            text="Ready. Drop an IFC file above to begin.",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.grid(row=1, column=0, padx=16, pady=8, sticky="w")
        
        self.file_info_label = ctk.CTkLabel(
            footer_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.file_info_label.grid(row=1, column=1, padx=16, pady=8, sticky="e")

    def _setup_dnd(self):
        """Register drag-and-drop file target."""
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop_file)

    def _check_dialux_status(self):
        """Update DIALux detection badge."""
        windows = get_dialux_windows()
        if windows:
            self.dialux_status_label.configure(
                text="🟢 DIALux evo Active",
                fg_color="#194d29",
                text_color="#64ff88"
            )
        else:
            exe = find_dialux_executable()
            if exe:
                self.dialux_status_label.configure(
                    text="⚪ DIALux evo Ready (Offline)",
                    fg_color="#2b313a",
                    text_color="#a0aec0"
                )
            else:
                self.dialux_status_label.configure(
                    text="⚠️ DIALux evo Not Found",
                    fg_color="#4d2919",
                    text_color="#ffaa64"
                )

    def _browse_file(self):
        """Open file dialog for IFC selection."""
        if self.is_processing:
            return
        path = filedialog.askopenfilename(
            title="Select IFC File",
            filetypes=[("IFC BIM Files", "*.ifc"), ("All Files", "*.*")]
        )
        if path:
            self.load_ifc_file(path)

    def _on_drop_file(self, event):
        """Handle file dropped onto window."""
        if self.is_processing:
            return
        data = event.data
        # On Windows, path may be surrounded by curly braces if containing spaces
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        path = data.strip()
        if os.path.isfile(path) and path.lower().endswith(".ifc"):
            self.load_ifc_file(path)
        else:
            messagebox.showwarning("Invalid File", "Please drop a valid .IFC file.")

    def load_ifc_file(self, file_path: str):
        """Parse IFC file asynchronously."""
        self.current_ifc_path = file_path
        self.is_processing = True
        self.drop_label.configure(text=f"⏳ Loading {os.path.basename(file_path)}...")
        self.status_label.configure(text="Reading IFC schema, hierarchy, and building storeys...")
        self.progress_bar.set(0.15)
        
        def worker():
            try:
                inspector = IfcModelInspector(file_path)
                inspector.load()
                self.inspector = inspector
                self.after(0, self._on_ifc_loaded_success)
            except Exception as e:
                logger.error(f"Failed to load IFC: {e}", exc_info=True)
                self.after(0, lambda: self._on_ifc_loaded_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ifc_loaded_success(self):
        self.is_processing = False
        self.progress_bar.set(0)
        filename = os.path.basename(self.current_ifc_path)
        file_size_mb = os.path.getsize(self.current_ifc_path) / (1024 * 1024)
        
        self.drop_label.configure(text=f"✅ {filename}")
        self.drop_sublabel.configure(text=f"Size: {file_size_mb:.2f} MB | Drag another file to replace")
        self.file_info_label.configure(text=f"{self.inspector.total_elements_count} BIM elements")
        self.status_label.configure(text=f"Loaded: {self.inspector.project_name} ({self.inspector.schema})")
        
        self._populate_model_inspector()
        self._check_dialux_status()

    def _on_ifc_loaded_error(self, err_msg: str):
        self.is_processing = False
        self.progress_bar.set(0)
        self.drop_label.configure(text="❌ Error reading IFC file")
        self.drop_sublabel.configure(text="Click to try another file")
        self.status_label.configure(text=f"Error: {err_msg}")
        messagebox.showerror("IFC Load Error", f"Failed to load IFC file:\n{err_msg}")

    def _populate_model_inspector(self):
        """Fill the left panel with parsed metadata, storeys, and element filters."""
        for widget in self.model_panel.winfo_children():
            widget.destroy()
            
        summary = self.inspector.get_summary()
        
        # Project Info Card
        card = ctk.CTkFrame(self.model_panel, corner_radius=8, fg_color=("gray85", "#252932"))
        card.pack(fill="x", padx=4, pady=6)
        
        ctk.CTkLabel(card, text=f"🏢 {summary['project_name']}", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(card, text=f"Tool: {summary['authoring_app']}", font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(card, text=f"Schema: {summary['schema']} | Length Unit: {summary['detected_unit']}", font=ctk.CTkFont(size=11), text_color="#38bdf8", anchor="w").pack(fill="x", padx=10, pady=(1, 8))
        
        # Storeys Section
        if summary["storeys"]:
            storey_card = ctk.CTkFrame(self.model_panel, corner_radius=8, fg_color=("gray85", "#252932"))
            storey_card.pack(fill="x", padx=4, pady=6)
            
            ctk.CTkLabel(storey_card, text="📍 Building Storeys", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
            
            self.storey_vars.clear()
            for s in summary["storeys"]:
                name = s["name"]
                elev = s["elevation"]
                var = ctk.BooleanVar(value=True)
                self.storey_vars[name] = var
                chk = ctk.CTkCheckBox(storey_card, text=f"{name} (Elev: {elev:.2f}m)", variable=var, font=ctk.CTkFont(size=11))
                chk.pack(anchor="w", padx=14, pady=2)
            ctk.CTkLabel(storey_card, text="").pack(pady=2)
            
        # Category Filters Section
        cat_card = ctk.CTkFrame(self.model_panel, corner_radius=8, fg_color=("gray85", "#252932"))
        cat_card.pack(fill="x", padx=4, pady=6)
        
        ctk.CTkLabel(cat_card, text="🧱 Architectural Categories", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        
        # Default active categories: building envelope + openings + structural
        default_active = {"IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcRoof", "IfcDoor", "IfcWindow", "IfcCurtainWall", "IfcColumn", "IfcBeam", "IfcStair"}
        
        self.category_vars.clear()
        for cls_name, count in summary["category_counts"].items():
            if count == 0:
                continue
            is_checked = cls_name in default_active
            var = ctk.BooleanVar(value=is_checked)
            self.category_vars[cls_name] = var
            clean_name = cls_name.replace("Ifc", "")
            chk = ctk.CTkCheckBox(cat_card, text=f"{clean_name} ({count})", variable=var, font=ctk.CTkFont(size=11))
            chk.pack(anchor="w", padx=14, pady=2)
        ctk.CTkLabel(cat_card, text="").pack(pady=2)

    def _on_unit_change(self, choice):
        """Handle unit scale dropdown change."""
        pass

    def _get_active_categories(self) -> List[str]:
        return [cls for cls, var in self.category_vars.items() if var.get()]

    def _get_active_storeys(self) -> List[str]:
        return [s for s, var in self.storey_vars.items() if var.get()]

    def _get_scale_factor(self) -> float:
        choice = self.unit_combo.get()
        if "Automatic" in choice and self.inspector:
            return self.inspector.unit_scale_to_meters
        elif "Meters" in choice:
            return 1.0
        elif "Millimeters" in choice:
            return 0.001
        elif "Feet" in choice:
            return 0.3048
        elif "Inches" in choice:
            return 0.0254
        return 1.0

    def _on_send_to_dialux(self):
        """Execute full Send to DIALux action."""
        if not self.inspector or not self.current_ifc_path:
            messagebox.showinfo("No File", "Please drop or select an IFC file first.")
            return
            
        categories = self._get_active_categories()
        if not categories:
            messagebox.showwarning("No Categories", "Please select at least one architectural category.")
            return
            
        base_name = os.path.splitext(os.path.basename(self.current_ifc_path))[0]
        safe_name = sanitize_filename(base_name)
        export_dir = os.path.join(get_default_export_dir(), safe_name)
        output_obj = os.path.join(export_dir, f"{safe_name}.obj")
        
        self.is_processing = True
        self.btn_send.configure(state="disabled", text="⏳ Converting...")
        self.progress_bar.set(0.1)
        
        def worker():
            try:
                exporter = DialuxObjExporter(self.inspector)
                scale = self._get_scale_factor()
                
                def progress(cur, tot, desc):
                    pct = cur / max(tot, 1)
                    self.after(0, lambda: self._update_progress(pct, desc))
                    
                result = exporter.export(
                    output_obj_path=output_obj,
                    selected_categories=categories,
                    selected_storeys=self._get_active_storeys() if self.storey_vars else None,
                    scale_factor=scale,
                    group_by="storey",
                    progress_callback=progress
                )
                
                self.last_exported_obj = result["obj_path"]
                
                # Execute DIALux bridge transfer
                bridge_result = send_to_dialux(self.last_exported_obj)
                
                self.after(0, lambda: self._on_send_complete(result, bridge_result))
            except Exception as e:
                logger.error(f"Send to DIALux failed: {e}", exc_info=True)
                self.after(0, lambda: self._on_export_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_send_complete(self, export_res: dict, bridge_res: dict):
        self.is_processing = False
        self.btn_send.configure(state="normal", text="🚀  Send to DIALux evo")
        self.progress_bar.set(1.0)
        self.status_label.configure(text=bridge_res.get("message", "Sent to DIALux evo successfully!"))
        self._check_dialux_status()
        
        msg = (
            f"🎉 Exported & Transferred to DIALux evo!\n\n"
            f"• Output File: {os.path.basename(export_res['obj_path'])}\n"
            f"• Geometry: {export_res['total_vertices']} vertices, {export_res['total_faces']} triangles\n"
            f"• Export Time: {export_res['elapsed_seconds']:.2f} seconds\n\n"
            f"Clipboard: File copied in CF_HDROP format.\n"
            f"In DIALux evo: Press Ctrl+V, or drag the file into your 3D view!"
        )
        messagebox.showinfo("Send to DIALux Complete", msg)

    def _on_export_obj_custom(self):
        """Export OBJ with custom destination file dialog."""
        if not self.inspector or not self.current_ifc_path:
            messagebox.showinfo("No File", "Please drop an IFC file first.")
            return
            
        base_name = os.path.splitext(os.path.basename(self.current_ifc_path))[0]
        out_path = filedialog.asksaveasfilename(
            title="Save DIALux OBJ File",
            initialfile=f"{base_name}.obj",
            filetypes=[("Wavefront OBJ", "*.obj")]
        )
        if not out_path:
            return
            
        self._run_obj_export(out_path)

    def _run_obj_export(self, target_path: str):
        self.is_processing = True
        self.status_label.configure(text="Exporting custom OBJ...")
        self.progress_bar.set(0.1)
        
        def worker():
            try:
                exporter = DialuxObjExporter(self.inspector)
                scale = self._get_scale_factor()
                
                def progress(cur, tot, desc):
                    pct = cur / max(tot, 1)
                    self.after(0, lambda: self._update_progress(pct, desc))
                    
                res = exporter.export(
                    output_obj_path=target_path,
                    selected_categories=self._get_active_categories(),
                    selected_storeys=self._get_active_storeys() if self.storey_vars else None,
                    scale_factor=scale,
                    group_by="storey",
                    progress_callback=progress
                )
                self.last_exported_obj = res["obj_path"]
                self.after(0, lambda: self._on_custom_obj_complete(res))
            except Exception as e:
                self.after(0, lambda: self._on_export_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_custom_obj_complete(self, res: dict):
        self.is_processing = False
        self.progress_bar.set(1.0)
        self.status_label.configure(text=f"Exported OBJ: {os.path.basename(res['obj_path'])}")
        messagebox.showinfo("OBJ Export Complete", f"File saved:\n{res['obj_path']}")

    def _on_export_dxf(self):
        """Export 3D DXF CAD underlay."""
        if not self.inspector or not self.current_ifc_path:
            messagebox.showinfo("No File", "Please drop an IFC file first.")
            return
            
        base_name = os.path.splitext(os.path.basename(self.current_ifc_path))[0]
        out_path = filedialog.asksaveasfilename(
            title="Save 3D DXF File",
            initialfile=f"{base_name}_3D.dxf",
            filetypes=[("AutoCAD DXF", "*.dxf")]
        )
        if not out_path:
            return
            
        self.is_processing = True
        self.status_label.configure(text="Generating 3D DXF underlay...")
        self.progress_bar.set(0.1)
        
        def worker():
            try:
                exporter = DialuxDxfExporter(self.inspector)
                scale = self._get_scale_factor()
                
                def progress(cur, tot, desc):
                    pct = cur / max(tot, 1)
                    self.after(0, lambda: self._update_progress(pct, desc))
                    
                res = exporter.export(
                    output_dxf_path=out_path,
                    selected_categories=self._get_active_categories(),
                    selected_storeys=self._get_active_storeys() if self.storey_vars else None,
                    scale_factor=scale,
                    progress_callback=progress
                )
                self.after(0, lambda: self._on_dxf_complete(res))
            except Exception as e:
                self.after(0, lambda: self._on_export_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_dxf_complete(self, res: dict):
        self.is_processing = False
        self.progress_bar.set(1.0)
        self.status_label.configure(text=f"Exported DXF: {os.path.basename(res['dxf_path'])}")
        messagebox.showinfo("DXF Export Complete", f"3D DXF file saved:\n{res['dxf_path']}")

    def _on_open_folder(self):
        """Reveal exported files in Windows Explorer."""
        if self.last_exported_obj and os.path.exists(self.last_exported_obj):
            reveal_in_explorer(self.last_exported_obj)
        else:
            default_dir = get_default_export_dir()
            os.startfile(default_dir)

    def _update_progress(self, pct: float, desc: str):
        self.progress_bar.set(pct)
        self.status_label.configure(text=desc)

    def _on_export_error(self, err_msg: str):
        self.is_processing = False
        self.btn_send.configure(state="normal", text="🚀  Send to DIALux evo")
        self.progress_bar.set(0)
        self.status_label.configure(text=f"Export failed: {err_msg}")
        messagebox.showerror("Export Error", f"Conversion failed:\n{err_msg}")


def main():
    app = DialuxIFCApp()
    app.mainloop()


if __name__ == "__main__":
    main()
