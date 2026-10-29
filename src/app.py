"""DIALux IFC Bridge desktop interface - Modern, high-resilience UI."""

from __future__ import annotations

import os
import json
import queue
import threading
import webbrowser
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .coordinate_transform import CoordinateTransform
from .architecture_inventory import IfcArchitectureInventoryExporter
from .dialux_bridge import (
    copy_files_to_clipboard,
    get_dialux_connection_status,
    reveal_in_explorer,
    send_to_dialux,
)
from .dxf_exporter import DialuxDxfExporter
from .ifc_parser import IfcModelInspector
from .native_exporter import (
    DialuxNativeProjectExporter,
    canonicalize_room_storey_assignments,
)
from .obj_exporter import UNIT_PER_METER, DialuxObjExporter
from .stf_exporter import DialuxStfExporter
from .utils import (
    APP_VERSION,
    export_debug_info,
    get_default_export_dir,
    get_log_path,
    load_config,
    logger,
    sanitize_filename,
    save_config,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    class _DnDBase(TkinterDnD.DnDWrapper):
        pass

except ImportError:
    DND_FILES = None

    class _DnDBase:
        pass


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DialuxIFCApp(ctk.CTk, _DnDBase):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DIALux IFC Bridge {APP_VERSION}")
        self.geometry("1100x820")
        self.minsize(940, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.current_ifc_path: str | None = None
        self.inspector: IfcModelInspector | None = None
        self.last_export: dict[str, Any] | None = None
        self._busy = False
        self._cancel_event: threading.Event | None = None
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._config = load_config()
        self._category_vars: dict[str, tk.BooleanVar] = {}
        self._storey_vars: dict[str, tk.BooleanVar] = {}

        self.include_spaces = tk.BooleanVar(self, self._config.get("include_space_meshes") is True)
        self.include_curtain_walls = tk.BooleanVar(self, self._config.get("include_curtain_walls") is not False)
        self.include_native_geometry = tk.BooleanVar(self, self._config.get("include_native_geometry") is not False)
        self.preserve_names = tk.BooleanVar(self, self._config.get("preserve_names") is not False)
        self.rebase_origin = tk.BooleanVar(self, self._config.get("rebase_origin") is not False)
        unit = self._config.get("output_unit")
        grouping = self._config.get("grouping")
        self.output_unit = tk.StringVar(
            self,
            unit if isinstance(unit, str) and unit in {"metres", "millimetres", "feet", "inches"} else "metres",
        )
        self.grouping = tk.StringVar(
            self,
            grouping
            if isinstance(grouping, str) and grouping in {"storey_and_category", "storey", "category"}
            else "storey_and_category",
        )
        self.room_defaults = {
            "workplane_m": tk.StringVar(self, str(self._config.get("workplane_m", 0.85))),
        }

        self._build_ui()
        self._setup_drag_drop()
        self._refresh_dialux_status()
        self.after(100, self._drain_events)
        self.after(4000, self._schedule_dialux_status)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Header Banner
        header = ctk.CTkFrame(self, corner_radius=0, height=68, fg_color=("#1f242d", "#14171d"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=20, pady=12, sticky="w")
        ctk.CTkLabel(
            logo_frame,
            text="DIALux IFC Bridge",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Native rooms and levels, with a coordinated IFC geometry package",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).grid(row=0, column=1, sticky="w", padx=10)

        status_box = ctk.CTkFrame(header, fg_color="transparent")
        status_box.grid(row=0, column=2, padx=20, pady=12, sticky="e")
        self.dialux_status = ctk.CTkLabel(
            status_box,
            text="Checking DIALux...",
            corner_radius=8,
            fg_color="#293241",
            font=ctk.CTkFont(size=11, weight="bold"),
            padx=12,
            pady=4,
        )
        self.dialux_status.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            status_box,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(side="left")

        # 2. Hero Drop Zone
        self.drop_frame = ctk.CTkFrame(
            self,
            border_width=2,
            border_color="#1f6aa5",
            corner_radius=12,
            fg_color=("#252c38", "#181d26"),
        )
        self.drop_frame.grid(row=1, column=0, padx=20, pady=(12, 6), sticky="ew")
        self.drop_frame.grid_columnconfigure(0, weight=1)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="Drop an IFC file here, or click to browse",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("gray10", "gray90"),
        )
        self.drop_label.grid(row=0, column=0, padx=12, pady=(12, 2))
        self.drop_hint = ctk.CTkLabel(
            self.drop_frame,
            text="Inspect model units, storeys, spaces, and architectural geometry",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.drop_hint.grid(row=1, column=0, padx=12, pady=(0, 10))

        self.drop_label.bind("<Button-1>", lambda _event: self._choose_ifc())
        self.drop_hint.bind("<Button-1>", lambda _event: self._choose_ifc())
        self.drop_frame.bind("<Button-1>", lambda _event: self._choose_ifc())

        # 3. Quick Action Bar (Primary Workflow)
        action_bar = ctk.CTkFrame(self, corner_radius=10, fg_color=("#222834", "#151921"))
        action_bar.grid(row=2, column=0, padx=20, pady=4, sticky="ew")
        action_bar.grid_columnconfigure(0, weight=3)
        action_bar.grid_columnconfigure((1, 2, 3), weight=1)

        self.primary_export_btn = ctk.CTkButton(
            action_bar,
            text="Create Native Room-Boundary Project + OBJ Package",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#107c41",
            hover_color="#0e6b37",
            command=self._choose_export_path,
        )
        self.primary_export_btn.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.quick_copy_btn = ctk.CTkButton(
            action_bar,
            text="Copy OBJ + MTL",
            height=36,
            command=self._copy_last_export,
        )
        self.quick_copy_btn.grid(row=0, column=1, padx=4, pady=8, sticky="ew")

        self.quick_dxf_btn = ctk.CTkButton(
            action_bar,
            text="Export 3D DXF",
            height=36,
            command=self._choose_dxf_path,
        )
        self.quick_dxf_btn.grid(row=0, column=2, padx=4, pady=8, sticky="ew")

        self.quick_folder_btn = ctk.CTkButton(
            action_bar,
            text="Open Package Folder",
            height=36,
            command=self._open_output_folder,
        )
        self.quick_folder_btn.grid(row=0, column=3, padx=(4, 8), pady=8, sticky="ew")

        # 4. Tabview (Model, Options, Diagnostic Tools)
        self.tabs = ctk.CTkTabview(
            self,
            corner_radius=12,
            segmented_button_selected_color="#107c41",
            segmented_button_selected_hover_color="#0e6b37",
        )
        self.tabs.grid(row=3, column=0, padx=20, pady=(4, 8), sticky="nsew")
        self.tabs.add("Model")
        self.tabs.add("Options")
        self.tabs.add("Diagnostics")
        self._build_model_tab()
        self._build_options_tab()
        self._build_tools_tab()

        # 5. Footer (Progress, Status, Cancel)
        footer = ctk.CTkFrame(self, corner_radius=0, height=48, fg_color=("#1a1e26", "#111419"))
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(footer, height=5, progress_color="#38bdf8")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.progress.set(0)

        self.status = ctk.CTkLabel(
            footer,
            text="Ready. Drop an IFC file above to begin.",
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.status.grid(row=1, column=0, padx=16, pady=8, sticky="ew")

        self.cancel_button = ctk.CTkButton(
            footer,
            text="Cancel",
            width=80,
            height=28,
            fg_color="#8b2626",
            hover_color="#6e1e1e",
            command=self._cancel_operation,
            state="disabled",
        )
        self.cancel_button.grid(row=1, column=1, padx=14, pady=8)

    def _build_model_tab(self) -> None:
        tab = self.tabs.tab("Model")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Project Info Summary Card
        self.summary_card = ctk.CTkFrame(tab, corner_radius=8, fg_color=("#272e3b", "#1c212b"))
        self.summary_card.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        self.summary_card.grid_columnconfigure(0, weight=1)

        self.summary_label = ctk.CTkLabel(
            self.summary_card,
            text="No IFC loaded. Drop a file above to inspect storeys, spaces, and elements.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w",
            justify="left",
            padx=12,
            pady=8,
        )
        self.summary_label.grid(row=0, column=0, sticky="ew")

        # Scrollable Storeys and Categories Frame
        self.model_scroll = ctk.CTkScrollableFrame(tab, label_text="Building Structure & Categories")
        self.model_scroll.grid(row=1, column=0, padx=8, pady=4, sticky="nsew")
        self.model_scroll.grid_columnconfigure(0, weight=1)

        self.model_placeholder = ctk.CTkLabel(
            self.model_scroll,
            text="Drop an IFC file above to inspect storeys and architectural categories.",
            text_color="gray",
            pady=40,
        )
        self.model_placeholder.pack(fill="x", expand=True)

    def _build_options_tab(self) -> None:
        tab = self.tabs.tab("Options")
        tab.grid_columnconfigure((0, 1), weight=1)

        # General Geometry & BIM Card
        geom_card = ctk.CTkFrame(tab, corner_radius=10)
        geom_card.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(geom_card, text="BIM Conversion Settings", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self._option_checkbox(geom_card, "Include curtain walls (frames & glass)", self.include_curtain_walls)
        self._option_checkbox(geom_card, "Create native DIALux mesh objects from IFC geometry", self.include_native_geometry)
        self._option_checkbox(geom_card, "Preserve original IFC element names", self.preserve_names)
        self._option_checkbox(
            geom_card,
            "Rebase model to room-bounds center (maximizes precision)",
            self.rebase_origin,
        )
        self._option_checkbox(
            geom_card,
            "Export IFC space/zone volumes as OBJ meshes (diagnostic)",
            self.include_spaces,
        )
        self._add_setting_traces()

        # Coordinate & Units Card
        unit_card = ctk.CTkFrame(tab, corner_radius=10)
        unit_card.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        unit_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(unit_card, text="Units & Grouping", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(12, 8), sticky="w"
        )

        ctk.CTkLabel(unit_card, text="Output coordinate unit:").grid(row=1, column=0, padx=14, pady=6, sticky="w")
        ctk.CTkOptionMenu(
            unit_card,
            values=["metres", "millimetres", "feet", "inches"],
            variable=self.output_unit,
            command=lambda _val: self._save_preferences(),
        ).grid(row=1, column=1, padx=14, pady=6, sticky="e")

        ctk.CTkLabel(unit_card, text="OBJ hierarchy grouping:").grid(row=2, column=0, padx=14, pady=6, sticky="w")
        ctk.CTkOptionMenu(
            unit_card,
            values=["storey_and_category", "storey", "category"],
            variable=self.grouping,
            command=lambda _val: self._save_preferences(),
        ).grid(row=2, column=1, padx=14, pady=6, sticky="e")

        ctk.CTkLabel(unit_card, text="Workplane height (m):").grid(row=3, column=0, padx=14, pady=6, sticky="w")
        ctk.CTkEntry(unit_card, textvariable=self.room_defaults["workplane_m"], width=100).grid(
            row=3, column=1, padx=14, pady=6, sticky="e"
        )

        # Technical Info Card
        info_card = ctk.CTkFrame(tab, corner_radius=10)
        info_card.grid(row=1, column=0, columnspan=2, padx=8, pady=(4, 8), sticky="ew")
        ctk.CTkLabel(
            info_card,
            text=(
                "The native .evo contains room boundaries and per-product IFC mesh objects grouped by storey. "
                "Mesh objects preserve IFC GlobalIds and types in the audit, but are not parametric DIALux walls, "
                "doors, windows, or luminaires; native reflectance and lighting behavior are not inferred."
            ),
            wraplength=880,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="#38bdf8",
        ).pack(anchor="w", padx=14, pady=10)

    def _build_tools_tab(self) -> None:
        tab = self.tabs.tab("Diagnostics")
        tab.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(tab, corner_radius=10)
        card.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Diagnostics & Troubleshooting", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        ctk.CTkLabel(
            card,
            text="If you encounter conversion issues or need to file a bug report, use the tools below.",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkButton(
            btn_row,
            text="💾 Save Troubleshooting Bundle (.zip)",
            command=self._save_debug_bundle,
            height=34,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="📄 View App Log",
            command=self._open_app_log,
            height=34,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_row,
            text="📁 Open Exports Folder",
            command=self._open_output_folder,
            height=34,
        ).pack(side="left", padx=10)

    def _option_checkbox(self, parent: ctk.CTkFrame, label: str, variable: tk.BooleanVar) -> None:
        ctk.CTkCheckBox(
            parent,
            text=label,
            variable=variable,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=14, pady=5)

    def _add_setting_traces(self) -> None:
        for variable in (
            self.include_spaces,
            self.include_curtain_walls,
            self.include_native_geometry,
            self.preserve_names,
            self.rebase_origin,
        ):
            variable.trace_add("write", lambda *_args: self._save_preferences())
        self.output_unit.trace_add("write", lambda *_args: self._save_preferences())
        self.grouping.trace_add("write", lambda *_args: self._save_preferences())

    def _setup_drag_drop(self) -> None:
        if DND_FILES is None:
            return
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except tk.TclError as exc:
            logger.warning("Drag-and-drop is unavailable: %s", exc)

    def _choose_ifc(self) -> None:
        if self._busy:
            return
        path = filedialog.askopenfilename(
            title="Open IFC BIM Model",
            filetypes=[("IFC Models (*.ifc)", "*.ifc"), ("All Files (*.*)", "*.*")],
        )
        if path:
            self._load_ifc(path)

    def _on_drop(self, event: Any) -> None:
        if self._busy:
            return
        try:
            paths = self.tk.splitlist(event.data)
        except tk.TclError as exc:
            messagebox.showerror("Drop Failed", f"Could not read the dropped file path:\n{exc}")
            return
        if not paths or not os.path.isfile(paths[0]) or not paths[0].lower().endswith(".ifc"):
            messagebox.showwarning("Unsupported File", "Please drop a valid .ifc file.")
            return
        self._load_ifc(paths[0])

    def _load_ifc(self, path: str) -> None:
        if self._busy:
            return
        try:
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
        except OSError as exc:
            messagebox.showerror("Could Not Read IFC", f"The selected file is unavailable:\n{exc}")
            return
        self._busy = True
        self._cancel_event = threading.Event()
        self.drop_label.configure(text=f"⏳  Loading {os.path.basename(path)} ({file_size_mb:.1f} MB)...")
        self._set_progress(0.01, f"Opening {os.path.basename(path)} ({file_size_mb:.1f} MB) - parsing IFC schema...")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._set_busy_controls(True)

        def worker() -> None:
            try:
                inspector = IfcModelInspector(path)

                def progress(fraction: float, description: str) -> None:
                    self._events.put(("progress", (fraction, description)))

                inspector.load(progress, self._cancel_event)
                self._events.put(("load_complete", inspector))
            except Exception as exc:
                logger.exception("IFC load failed")
                self._events.put(("operation_error", ("IFC Load Failed", exc)))

        threading.Thread(target=worker, name="ifc-loader", daemon=True).start()

    def _choose_export_path(self) -> None:
        if not self._require_model():
            return
        output_dir = filedialog.askdirectory(
            title="Select Output Folder for the DIALux Model Package",
            initialdir=get_default_export_dir(),
        )
        if output_dir:
            self._start_package_export(output_dir)

    def _start_package_export(self, output_dir: str) -> None:
        if not self._require_model() or self._busy:
            return
        categories = [name for name, variable in self._category_vars.items() if variable.get()]
        if not categories:
            messagebox.showwarning("No Categories Selected", "Select at least one IFC category in the Model tab.")
            return
        storeys = [name for name, variable in self._storey_vars.items() if variable.get()]
        if not storeys:
            messagebox.showwarning("No Storeys Selected", "Select at least one storey in the Model tab.")
            return
        try:
            defaults = {name: float(variable.get()) for name, variable in self.room_defaults.items()}
            DialuxStfExporter(self.inspector, **defaults)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid Room Defaults", str(exc))
            return
        self._save_preferences()
        options = {
            "categories": categories,
            "storeys": storeys,
            "target_unit": self.output_unit.get(),
            "group_by": self.grouping.get(),
            "include_spaces": self.include_spaces.get(),
            "include_curtain_walls": self.include_curtain_walls.get(),
            "include_native_geometry": self.include_native_geometry.get(),
            "preserve_names": self.preserve_names.get(),
            "rebase_origin": self.rebase_origin.get(),
            "room_defaults": defaults,
        }
        self._begin_operation("Preparing DIALux model package...")
        inspector = self.inspector

        def worker() -> None:
            package_dir: str | None = None
            stage = "creating the package folder"
            completed_steps: list[str] = []
            native_error: str | None = None
            bridge_error: str | None = None

            def write_manifest(status: str, error: str | None = None) -> None:
                if package_dir is None:
                    return
                manifest = {
                    "format": "DIALux IFC Bridge package status",
                    "format_version": 1,
                    "application_version": APP_VERSION,
                    "status": status,
                    "source_file": inspector.file_path,
                    "completed_steps": completed_steps,
                    "current_or_failed_step": stage,
                    "warnings": [item for item in (native_error, bridge_error) if item]
                    + (native_result.get("native_geometry_warnings", []) if native_result else [])
                    + (native_result.get("geometry_warnings", []) if native_result else []),
                    "error": error,
                }
                manifest_path = os.path.join(package_dir, "package_status.json")
                temporary_path = manifest_path + ".tmp"
                try:
                    with open(temporary_path, "x", encoding="utf-8", newline="\n") as manifest_file:
                        json.dump(manifest, manifest_file, indent=2, ensure_ascii=False, allow_nan=False)
                        manifest_file.write("\n")
                    os.replace(temporary_path, manifest_path)
                except OSError:
                    logger.exception("Could not write the package status manifest")
                    try:
                        if os.path.exists(temporary_path):
                            os.remove(temporary_path)
                    except OSError:
                        logger.exception("Could not remove a partial package status manifest")

            try:
                base_name = sanitize_filename(os.path.splitext(os.path.basename(inspector.file_path))[0])
                package_dir = os.path.join(output_dir, base_name + "_DIALux")
                suffix = 2
                while True:
                    try:
                        os.mkdir(package_dir)
                        break
                    except FileExistsError:
                        package_dir = os.path.join(output_dir, f"{base_name}_DIALux_{suffix}")
                        suffix += 1
                completed_steps.append("package folder created")
                obj_path = os.path.join(package_dir, base_name + ".obj")
                exporter = DialuxObjExporter(inspector)

                def progress(fraction: float, description: str) -> None:
                    self._events.put(("progress", (0.1 + fraction * 0.65, description)))

                native_result = None
                room_records = None
                if inspector.ifc_file.by_type("IfcSpace"):
                    stage = "extracting native room contours"
                    try:
                        room_exporter = DialuxStfExporter(inspector, **options["room_defaults"])
                        extracted_room_records = room_exporter.extract_rooms(
                            progress_callback=lambda fraction, description: self._events.put(
                                ("progress", (fraction * 0.1, description))
                            ),
                            cancel_event=self._cancel_event,
                        )
                        canonical_records = canonicalize_room_storey_assignments(
                            extracted_room_records
                        )
                        selected_storeys = set(options["storeys"])
                        room_records = [
                            room
                            for room in canonical_records
                            if room["source_storey"] in selected_storeys
                        ]
                        if not room_records:
                            raise ValueError(
                                "The selected storeys contain no rooms with usable geometry."
                            )
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        native_error = str(exc)
                        logger.exception("Native DIALux building, level and room extraction encountered an issue")
                else:
                    native_error = "No IFC spaces were found for native room creation."

                coordinate_transform = None
                if room_records:
                    if options["rebase_origin"]:
                        coordinate_transform = CoordinateTransform.centered_on_room_contours(
                            (room["contour_m"] for room in room_records),
                            source_unit_to_meters=inspector.unit_scale_to_meters,
                            output_units_per_meter=UNIT_PER_METER[options["target_unit"]],
                            scale_factor=1.0,
                        )
                    else:
                        coordinate_transform = CoordinateTransform(
                            source_unit_to_meters=inspector.unit_scale_to_meters,
                            origin_basis="world_origin",
                            output_units_per_meter=UNIT_PER_METER[options["target_unit"]],
                        )
                stage = "exporting OBJ, IFC metadata and room schedule"
                result = exporter.export(
                    obj_path,
                    selected_categories=options["categories"],
                    selected_storeys=options["storeys"],
                    target_unit=options["target_unit"],
                    group_by=options["group_by"],
                    include_spaces=options["include_spaces"],
                    include_curtain_walls=options["include_curtain_walls"],
                    preserve_names=options["preserve_names"],
                    rebase_origin=options["rebase_origin"],
                    coordinate_transform=coordinate_transform,
                    progress_callback=progress,
                    cancel_event=self._cancel_event,
                )
                completed_steps.append("OBJ, MTL, IFC metadata and room schedule exported")
                stage = "writing the IFC architecture inventory"
                inventory_path = os.path.join(
                    package_dir,
                    base_name + "_architecture_inventory.json",
                )
                inventory_result = IfcArchitectureInventoryExporter(inspector).export(
                    inventory_path,
                    coordinate_transform=result["coordinate_transform"],
                    progress_callback=lambda fraction, description: self._events.put(
                        ("progress", (0.76 + fraction * 0.08, description))
                    ),
                    cancel_event=self._cancel_event,
                )
                result["architecture_inventory_path"] = inventory_result["inventory_path"]
                result["architecture_inventory_summary"] = inventory_result["summary"]
                completed_steps.append("IFC architecture inventory exported")
                if room_records:
                    stage = "creating and reload-verifying the native DIALux project"
                    try:
                        native_result = DialuxNativeProjectExporter().export(
                            inspector,
                            room_records,
                            os.path.join(package_dir, base_name + ".evo"),
                            coordinate_transform=result["coordinate_transform"],
                            workplane_m=options["room_defaults"]["workplane_m"],
                            include_native_geometry=options["include_native_geometry"],
                            progress_callback=lambda fraction, description: self._events.put(
                                ("progress", (0.85 + fraction * 0.14, description))
                            ),
                            cancel_event=self._cancel_event,
                        )
                        native_counts = native_result.get("native_counts", {})
                        completed_steps.append(
                            "native DIALux project created and reload-verified: "
                            f"{native_result['room_count']} rooms, "
                            f"{native_counts.get('boundary_contour_count', 0)} boundary contours, "
                            f"{native_counts.get('generic_geometry_element_count', 0)} IFC mesh objects"
                        )
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        native_error = str(exc)
                        logger.exception("Native DIALux project creation failed")

                stage = "preparing the OBJ clipboard handoff"
                bridge_result = None
                try:
                    bridge_result = send_to_dialux(result["obj_path"], activate=False)
                except (OSError, ValueError) as exc:
                    bridge_error = str(exc)
                    logger.warning("Package export succeeded, but DIALux clipboard copy was unavailable: %s", exc)
                stage = "writing the package status manifest"
                status = "COMPLETE" if native_result else "PARTIAL"
                if bridge_error or (
                    native_result
                    and (native_result.get("native_geometry_warnings") or native_result.get("geometry_warnings"))
                ):
                    status = "COMPLETE_WITH_NOTICES" if native_result else "PARTIAL"
                write_manifest(status)
                self._events.put(
                    (
                        "package_complete",
                        (result, native_result, native_error, bridge_result, bridge_error),
                    )
                )
            except InterruptedError as exc:
                write_manifest("CANCELLED", str(exc))
                self._events.put(("operation_error", ("Package Preparation Cancelled", exc)))
            except Exception as exc:
                logger.exception("DIALux package preparation failed")
                write_manifest("FAILED", str(exc))
                self._events.put(("operation_error", ("Package Preparation Failed", exc)))

        threading.Thread(target=worker, name="ifc-exporter", daemon=True).start()

    def _choose_dxf_path(self) -> None:
        if not self._require_model() or self._busy:
            return
        initial = os.path.splitext(os.path.basename(self.current_ifc_path or "model.ifc"))[0] + ".dxf"
        path = filedialog.asksaveasfilename(
            title="Save 3D DXF Underlay",
            initialdir=get_default_export_dir(),
            initialfile=initial,
            defaultextension=".dxf",
            filetypes=[("AutoCAD DXF (*.dxf)", "*.dxf")],
        )
        if not path:
            return
        inspector = self.inspector
        categories = [name for name, variable in self._category_vars.items() if variable.get()]
        storeys = [name for name, variable in self._storey_vars.items() if variable.get()]
        target_unit = self.output_unit.get()
        coordinate_transform = None
        last_export = getattr(self, "last_export", None)
        if last_export is not None:
            current_source = os.path.normcase(os.path.abspath(inspector.file_path))
            previous_source = os.path.normcase(os.path.abspath(str(last_export.get("source_file") or "")))
            if (
                previous_source == current_source
                and set(last_export.get("selected_categories") or ()) == set(categories)
                and set(last_export.get("selected_storeys") or ()) == set(storeys)
                and last_export.get("output_unit") == target_unit
            ):
                coordinate_transform = last_export.get("coordinate_transform")
        self._begin_operation("Exporting 3D DXF underlay...")

        def worker() -> None:
            try:
                result = DialuxDxfExporter(inspector).export(
                    path,
                    selected_categories=categories,
                    selected_storeys=storeys,
                    target_unit=target_unit,
                    coordinate_transform=coordinate_transform,
                    progress_callback=lambda fraction, description: self._events.put(
                        ("progress", (fraction, description))
                    ),
                    cancel_event=self._cancel_event,
                )
                self._events.put(("dxf_complete", result))
            except Exception as exc:
                logger.exception("DXF export failed")
                self._events.put(("operation_error", ("DXF Export Failed", exc)))

        threading.Thread(target=worker, name="dxf-exporter", daemon=True).start()

    def _copy_last_export(self) -> None:
        if not self.last_export:
            messagebox.showinfo("No Export Available", "Export a DIALux model package first.")
            return
        try:
            paths = [self.last_export["obj_path"], self.last_export["mtl_path"]]
            copy_files_to_clipboard(paths)
            self.status.configure(text="✅ OBJ and MTL copied to clipboard. Paste into DIALux with Ctrl+V.")
            if os.name == "nt":
                from .dialux_bridge import activate_dialux

                activate_dialux()
            messagebox.showinfo(
                "Copied to Clipboard",
                "OBJ and MTL files are ready on your Windows clipboard.\n"
                "Switch to DIALux evo and press Ctrl+V to paste the 3D model into your view.",
            )
        except (OSError, ValueError) as exc:
            logger.exception("Clipboard copy failed")
            messagebox.showerror("Clipboard Error", str(exc))

    def _open_output_folder(self) -> None:
        if self.last_export:
            path = self.last_export["obj_path"]
        else:
            path = get_default_export_dir()
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        try:
            if os.name == "nt":
                os.startfile(folder)
            else:
                webbrowser.open(f"file://{folder}")
        except OSError as exc:
            messagebox.showerror("Could Not Open Folder", str(exc))

    def _open_app_log(self) -> None:
        lp = get_log_path()
        if os.path.exists(lp):
            try:
                os.startfile(lp)
            except OSError as exc:
                messagebox.showerror("Error Opening Log", str(exc))
        else:
            messagebox.showinfo("Log File", "No log file has been created yet.")

    def _save_debug_bundle(self) -> None:
        try:
            path = export_debug_info(self.current_ifc_path)
            if not path or not os.path.isfile(path):
                raise OSError("The troubleshooting bundle could not be created.")
            reveal_in_explorer(path)
            self.status.configure(text=f"Troubleshooting bundle saved: {path}")
            messagebox.showinfo(
                "Troubleshooting Bundle Saved",
                f"Diagnostic package created:\n{path}\n\nThis archive contains logs and system info to help diagnose any issues.",
            )
        except (OSError, ValueError) as exc:
            logger.exception("Could not save troubleshooting bundle")
            messagebox.showerror("Troubleshooting Bundle Failed", str(exc))

    def _require_model(self) -> bool:
        if self.inspector is None:
            messagebox.showinfo("No IFC Loaded", "Please select or drop an IFC file first.")
            return False
        return True

    def _begin_operation(self, description: str) -> None:
        self._busy = True
        self._cancel_event = threading.Event()
        self._set_busy_controls(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._set_progress(0, description)

    def _set_busy_controls(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.primary_export_btn.configure(state=state)
        self.quick_dxf_btn.configure(state=state)
        self.cancel_button.configure(state="normal" if busy else "disabled")

    def _cancel_operation(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status.configure(text="Cancellation requested; finishing current operation...")

    def _set_progress(self, fraction: float, description: str) -> None:
        if fraction > 0.04:
            try:
                self.progress.stop()
                self.progress.configure(mode="determinate")
            except Exception:
                pass
        self.progress.set(max(0.0, min(1.0, fraction)))
        self.status.configure(text=description)

    def _drain_events(self) -> None:
        try:
            while True:
                event, data = self._events.get_nowait()
                if event == "progress":
                    self._set_progress(*data)
                elif event == "load_complete":
                    self._on_load_complete(data)
                elif event == "package_complete":
                    self._on_package_complete(*data)
                elif event == "dxf_complete":
                    self._on_dxf_complete(data)
                elif event == "operation_error":
                    self._on_operation_error(*data)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._drain_events)

    def _on_load_complete(self, inspector: IfcModelInspector) -> None:
        self._finish_operation()
        self.inspector = inspector
        self.current_ifc_path = inspector.file_path
        self.last_export = None
        summary = inspector.get_summary()
        file_size_mb = os.path.getsize(inspector.file_path) / (1024 * 1024)
        filename = os.path.basename(inspector.file_path)

        self.drop_label.configure(text=f"✅  {filename}")
        self.drop_hint.configure(
            text=f"{file_size_mb:.2f} MB • {summary['schema']} • {summary['total_elements']:,} elements • Drag another to replace"
        )
        self.summary_label.configure(
            text=(
                f"🏢 Project: {summary['project_name']}   |   BIM Authoring: {summary['authoring_app']}\n"
                f"📏 Schema: {summary['schema']}   |   Source Units: {summary['detected_unit']} "
                f"({summary['unit_scale_to_meters']:.6g} m per unit)\n"
                f"📊 {summary['total_elements']:,} building elements   |   "
                f"{len(summary['rooms']):,} rooms/spaces   |   "
                f"{len(summary['storeys']):,} building storeys"
            )
        )
        self._populate_model(summary)
        self._set_progress(1.0, f"Ready: {filename} loaded successfully.")

    def _populate_model(self, summary: dict[str, Any]) -> None:
        for widget in self.model_scroll.winfo_children():
            widget.destroy()
        self._category_vars.clear()
        self._storey_vars.clear()

        # Storeys Section
        storey_header_frame = ctk.CTkFrame(self.model_scroll, fg_color="transparent")
        storey_header_frame.pack(fill="x", padx=4, pady=(6, 2))
        ctk.CTkLabel(
            storey_header_frame,
            text="📍 Building Storeys",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        def toggle_all_storeys(value: bool):
            for v in self._storey_vars.values():
                v.set(value)

        btn_box = ctk.CTkFrame(storey_header_frame, fg_color="transparent")
        btn_box.pack(side="right")
        ctk.CTkButton(btn_box, text="All", width=40, height=22, font=ctk.CTkFont(size=10), command=lambda: toggle_all_storeys(True)).pack(side="left", padx=2)
        ctk.CTkButton(btn_box, text="None", width=40, height=22, font=ctk.CTkFont(size=10), command=lambda: toggle_all_storeys(False)).pack(side="left", padx=2)

        storey_card = ctk.CTkFrame(self.model_scroll, corner_radius=8, fg_color=("#222834", "#181d26"))
        storey_card.pack(fill="x", padx=4, pady=2)

        for storey in summary["storeys"]:
            name = storey["name"]
            variable = tk.BooleanVar(self, True)
            self._storey_vars[name] = variable
            elevation_label = (
                f"elevation {storey['elevation']:.3f} m"
                if storey.get("elevation_defined", True)
                else "elevation inferred"
            )
            ctk.CTkCheckBox(
                storey_card,
                text=f"{name}  ({elevation_label})",
                variable=variable,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12, pady=4)

        # Architectural Categories Section
        cat_header_frame = ctk.CTkFrame(self.model_scroll, fg_color="transparent")
        cat_header_frame.pack(fill="x", padx=4, pady=(16, 2))
        ctk.CTkLabel(
            cat_header_frame,
            text="🧱 Architectural & Structural Categories",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        def toggle_all_cats(value: bool):
            for v in self._category_vars.values():
                v.set(value)

        btn_box2 = ctk.CTkFrame(cat_header_frame, fg_color="transparent")
        btn_box2.pack(side="right")
        ctk.CTkButton(btn_box2, text="All", width=40, height=22, font=ctk.CTkFont(size=10), command=lambda: toggle_all_cats(True)).pack(side="left", padx=2)
        ctk.CTkButton(btn_box2, text="None", width=40, height=22, font=ctk.CTkFont(size=10), command=lambda: toggle_all_cats(False)).pack(side="left", padx=2)

        cat_card = ctk.CTkFrame(self.model_scroll, corner_radius=8, fg_color=("#222834", "#181d26"))
        cat_card.pack(fill="x", padx=4, pady=2)

        for category, count in summary["category_counts"].items():
            variable = tk.BooleanVar(self, True)
            self._category_vars[category] = variable
            clean_name = category.replace("Ifc", "")
            ctk.CTkCheckBox(
                cat_card,
                text=f"{clean_name}  ({count:,})",
                variable=variable,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12, pady=4)

        self.tabs.set("Model")

    def _on_package_complete(
        self,
        result: dict[str, Any],
        native_result: dict[str, Any] | None,
        native_error: str | None,
        bridge_result: dict[str, Any] | None,
        bridge_error: str | None,
    ) -> None:
        self._finish_operation()
        self.last_export = result
        self._set_progress(1.0, f"✅ Package prepared: {os.path.basename(result['obj_path'])}")

        transfer_note = ""
        if bridge_result:
            transfer_note = f"\n\nClipboard Status:\n{bridge_result['message']}"
        elif bridge_error:
            transfer_note = f"\n\nClipboard Notice: {bridge_error}"

        if native_result:
            level_summary = ", ".join(
                f"{storey['name']} ({storey['elevation_m']:.2f}m)"
                for storey in native_result["storeys"]
            )
            native_counts = native_result.get("native_counts", {})
            native_note = (
                f"\n\n🏛️ Native DIALux Project Created:\n"
                f"• Levels: {native_result['storey_count']} ({level_summary})\n"
                f"• Native Rooms: {native_result['room_count']}\n"
                f"• Project File: {os.path.basename(native_result['project_path'])}\n"
                f"• Room Audit: {os.path.basename(native_result['room_audit_path'])}"
            )
            native_note += (
                f"\nNative room boundary contours: {native_counts.get('boundary_contour_count', 'verified')}"
                f"\nNative IFC mesh objects: {native_counts.get('generic_geometry_element_count', 0)}"
            )
            native_warnings = native_result.get("native_geometry_warnings", [])
            if native_warnings:
                native_note += f"\nIFC products skipped during native meshing: {len(native_warnings)} (see package_status.json)"
        else:
            native_note = f"\n\n⚠️ Native Project Notice: {native_error or 'Not created'}"

        msg = (
            f"🎉 DIALux Model Package Successfully Exported!\n\n"
            f"• Output Folder: {os.path.dirname(result['obj_path'])}\n"
            f"• Geometry: {result['total_vertices']:,} vertices, {result['total_faces']:,} triangles\n"
            f"• Architecture Inventory: {result['architecture_inventory_summary']['opening_count']} openings, "
            f"{result['architecture_inventory_summary']['filling_count']} fillings mapped\n"
            f"• Coordinates: Shared transform; output in {result['output_unit']}"
            f"{native_note}"
            f"{transfer_note}\n\n"
            f"Native building geometry is already in the .evo. The separate OBJ/MTL copy is available on the clipboard for reference."
        )

        if native_error:
            messagebox.showwarning("DIALux Package Ready (With Notices)", msg)
        else:
            messagebox.showinfo("DIALux Export Complete", msg)

        if native_result:
            try:
                DialuxNativeProjectExporter.open_project(native_result["project_path"])
            except Exception as exc:
                logger.warning("Could not auto-launch DIALux project: %s", exc)

    def _on_dxf_complete(self, result: dict[str, Any]) -> None:
        self._finish_operation()
        self._set_progress(1.0, f"✅ Exported DXF: {os.path.basename(result['dxf_path'])}")
        messagebox.showinfo(
            "3D DXF Export Complete",
            f"Saved {result['total_faces']:,} 3D faces:\n{result['dxf_path']}",
        )

    def _on_operation_error(self, title: str, error: Exception) -> None:
        self._finish_operation()
        if isinstance(error, InterruptedError):
            self._set_progress(0.0, "Operation was cancelled.")
            return

        error_text = str(error)
        logger.error("%s: %s", title, error_text, exc_info=True)
        self._set_progress(0.0, f"❌ {title}: {error_text}")

        # Categorize error guidance
        guidance = ""
        if "dialux" in error_text.lower() or "projectdata" in error_text.lower():
            guidance = "\n\n💡 Tip: Verify that DIALux evo 14 is installed in its default directory (C:\\Program Files\\DIAL GmbH\\DIALux)."
        elif "ifc" in error_text.lower() or "schema" in error_text.lower():
            guidance = "\n\n💡 Tip: Check that the IFC file was completely exported and is not truncated or locked by another application."

        formatted_msg = (
            f"An error occurred during {title.lower()}:\n\n"
            f"{error_text}"
            f"{guidance}\n\n"
            f"Logs are saved at:\n{get_log_path()}\n"
            f"You can also use 'Save Troubleshooting Bundle' in the Tools tab."
        )
        messagebox.showerror(title, formatted_msg)

    def _finish_operation(self) -> None:
        self._busy = False
        self._cancel_event = None
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate")
        except Exception:
            pass
        self._set_busy_controls(False)

    def _refresh_dialux_status(self) -> None:
        try:
            status = get_dialux_connection_status()
            if status["connected"]:
                text = "🟢 Connected to DIALux evo"
                color = "#194d29"
            elif status["running"]:
                text = "🟡 DIALux evo running"
                color = "#4d3f19"
            elif status["installed"]:
                text = "⚪ DIALux evo installed"
                color = "#293241"
            else:
                text = "⚠️ DIALux evo not detected"
                color = "#4d2919"
            self.dialux_status.configure(text=text, fg_color=color)
        except Exception as exc:
            logger.warning("DIALux status check failed: %s", exc)
            self.dialux_status.configure(text="DIALux status unavailable", fg_color="#4d2919")

    def _schedule_dialux_status(self) -> None:
        if self.winfo_exists():
            self._refresh_dialux_status()
            self.after(4000, self._schedule_dialux_status)

    def _save_preferences(self) -> None:
        config = {
            "include_space_meshes": self.include_spaces.get(),
            "include_curtain_walls": self.include_curtain_walls.get(),
            "include_native_geometry": self.include_native_geometry.get(),
            "preserve_names": self.preserve_names.get(),
            "rebase_origin": self.rebase_origin.get(),
            "output_unit": self.output_unit.get(),
            "grouping": self.grouping.get(),
            **{name: variable.get() for name, variable in self.room_defaults.items()},
        }
        try:
            save_config(config)
        except OSError as exc:
            logger.error("Could not save application settings: %s", exc)
            if hasattr(self, "status"):
                self.status.configure(text=f"Could not save settings: {exc}")

    def _on_close(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._save_preferences()
        self.destroy()


def main() -> None:
    app = DialuxIFCApp()
    app.mainloop()


if __name__ == "__main__":
    main()
