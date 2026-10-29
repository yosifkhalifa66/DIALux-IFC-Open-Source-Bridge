"""Create a DIALux evo project with native buildings, storeys, and rooms."""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import ifcopenshell.geom

from .coordinate_transform import CoordinateTransform
from .dialux_bridge import find_dialux_executable
from .ifc_parser import IfcModelInspector
from .utils import logger

ProgressCallback = Callable[[float, str], None]
NATIVE_HOST_NAME = "DialuxIfcNativeHost.exe"


def build_native_model_plan(
    inspector: IfcModelInspector,
    room_records: list[dict[str, Any]],
    *,
    coordinate_transform: CoordinateTransform | None = None,
    geometry_origin_m: tuple[float, float, float] | None = None,
    workplane_m: float = 0.85,
    include_native_geometry: bool = True,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    if not room_records:
        raise ValueError("The selected IFC storeys contain no rooms to create in DIALux.")
    if not math.isfinite(workplane_m) or workplane_m <= 0:
        raise ValueError("The room workplane must be a finite height greater than zero.")

    if coordinate_transform is not None and geometry_origin_m is not None:
        raise ValueError("Pass a coordinate transform or an origin offset, not both.")
    if coordinate_transform is None:
        origin = geometry_origin_m if geometry_origin_m is not None else (0.0, 0.0, 0.0)
        coordinate_transform = CoordinateTransform(
            origin_offset_m=tuple(float(value) for value in origin)
        )

    room_records = canonicalize_room_storey_assignments(room_records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for room in room_records:
        storey_name = str(room.get("source_storey") or "Unassigned").strip()
        if not storey_name or storey_name.casefold() == "unassigned":
            raise ValueError(
                f"Room '{room.get('name') or 'Unnamed room'}' has no IFC storey assignment. "
                "Correct its IFC spatial containment before creating native levels."
            )
        grouped.setdefault(storey_name, []).append(
            {
                **room,
                "source_ifc_storey": str(
                    room.get("source_ifc_storey") or storey_name
                ),
            }
        )
    storeys: list[dict[str, Any]] = []
    for name, rooms in grouped.items():
        elevations = [
            float(room["source_storey_elevation_m"])
            for room in rooms
            if room.get("source_storey_elevation_m") is not None
        ]
        if elevations and not all(math.isfinite(value) for value in elevations):
            raise ValueError(f"Storey '{name}' contains a non-finite IFC elevation.")
        if elevations and max(elevations) - min(elevations) > 0.01:
            raise ValueError(f"Rooms assigned to '{name}' report inconsistent IFC storey elevations.")
        floor_heights = [float(room["floor_z_m"]) for room in rooms]
        room_heights = [float(room["height_m"]) for room in rooms]
        if not all(math.isfinite(value) for value in floor_heights + room_heights):
            raise ValueError(f"Storey '{name}' contains a room with invalid geometry measurements.")
        elevation = statistics.median(floor_heights)
        if max(floor_heights) - min(floor_heights) > 0.02:
            raise ValueError(
                f"Rooms assigned to '{name}' have floor elevations that vary by more than 2 cm. "
                "A single native DIALux storey would misplace some rooms; correct the IFC storey "
                "assignment or split rooms onto their actual levels."
            )
        source_elevation = elevations[0] if elevations else None
        if source_elevation is not None and abs(source_elevation - elevation) > 0.05:
            logger.warning(
                "Storey '%s' IFC elevation (%.4f m) differs from its room-floor geometry (%.4f m); "
                "using room geometry so native rooms align with the exported OBJ.",
                name,
                source_elevation,
                elevation,
            )
        height = statistics.median(room_heights)
        if height <= workplane_m:
            raise ValueError(
                f"Storey '{name}' has a room height of {height:.3f} m, "
                f"not above the configured {workplane_m:.3f} m workplane."
            )

        native_rooms = []
        for index, room in enumerate(rooms, start=1):
            raw_name = " ".join(str(room.get("name") or f"Room {index}").split()).strip()
            name_for_dialux = raw_name[:80].rstrip() or f"Room {index}"
            contour = room.get("contour_m")
            if not isinstance(contour, (list, tuple)) or len(contour) < 3:
                raise ValueError(f"Room '{raw_name or index}' has no usable closed floor contour.")
            points = []
            for point in contour:
                if len(point) != 2:
                    raise ValueError(f"Room '{raw_name or index}' has an invalid floor contour point.")
                x, y = coordinate_transform.to_project_xy(
                    (float(point[0]), float(point[1]))
                )
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError(f"Room '{raw_name or index}' has non-finite floor coordinates.")
                points.append([x, y])
            geometry_diagnostics = room.get("geometry_diagnostics") or {}
            native_rooms.append(
                {
                    "name": name_for_dialux,
                    "ifc_global_id": str(room.get("ifc_global_id") or ""),
                    "source_name": str(room.get("name") or name_for_dialux),
                    "source_ifc_storey": str(room["source_ifc_storey"]),
                    "floor_z_m": float(room["floor_z_m"]),
                    "height_m": float(room["height_m"]),
                    "geometry_diagnostics": geometry_diagnostics,
                    "contour": points,
                }
            )

        storeys.append(
            {
                "name": name[:80],
                "elevation_m": coordinate_transform.to_project_elevation(elevation),
                "source_elevation_m": (
                    coordinate_transform.to_project_elevation(source_elevation)
                    if source_elevation is not None
                    else None
                ),
                "elevation_basis": "room geometry",
                "height_m": height,
                "rooms": native_rooms,
            }
        )

    storeys.sort(key=lambda storey: (storey["elevation_m"], storey["name"].casefold()))
    used_room_names: set[str] = set()
    for storey in storeys:
        for room in storey["rooms"]:
            base_name = room["name"].strip() or "Room"
            candidate = base_name
            suffix = 2
            while candidate.casefold() in used_room_names:
                candidate = f"{base_name} ({suffix})"
                suffix += 1
            used_room_names.add(candidate.casefold())
            room["name"] = candidate
    native_elements: list[dict[str, Any]] = []
    native_geometry_warnings: list[str] = []
    if include_native_geometry:
        native_elements, native_geometry_warnings = _build_native_elements(
            inspector, storeys, coordinate_transform,
            progress_callback=progress_callback, cancel_event=cancel_event,
        )
    return {
        "project_name": str(inspector.project_name or "IFC Building").strip() or "IFC Building",
        "site": _ifc_site_info(inspector),
        "workplane_m": workplane_m,
        "coordinate_transform": coordinate_transform.to_metadata(),
        "geometry_warnings": [
            warning
            for room in room_records
            for warning in (room.get("geometry_diagnostics") or {}).get("warnings", [])
        ],
        "native_geometry_warnings": native_geometry_warnings,
        "native_elements": native_elements,
        "storeys": storeys,
    }


def _build_native_elements(
    inspector: IfcModelInspector,
    storeys: list[dict[str, Any]],
    transform: CoordinateTransform,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Tessellate selected IFC products for native DIALux generic geometry objects."""
    model = getattr(inspector, "ifc_file", None)
    settings_factory = getattr(inspector, "get_tessellation_settings", None)
    if model is None or not callable(settings_factory):
        return [], []
    selected_storeys = {storey["name"] for storey in storeys}
    settings = settings_factory()
    result: list[dict[str, Any]] = []
    skipped: list[str] = []
    products = model.by_type("IfcProduct")
    candidates = [
        product for product in products
        if not product.is_a("IfcSpace") and not product.is_a("IfcOpeningElement")
        and inspector.element_to_storey.get(
            str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
        ) in selected_storeys
        and getattr(product, "Representation", None) is not None
    ]
    for product_index, product in enumerate(candidates, start=1):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Native IFC geometry conversion was cancelled.")
        if progress_callback and (product_index == 1 or product_index % 20 == 0):
            progress_callback(
                0.05 + 0.2 * product_index / max(1, len(candidates)),
                f"Tessellating native IFC geometry ({product_index:,}/{len(candidates):,})...",
            )
        guid = str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
        storey_name = inspector.element_to_storey.get(guid)
        try:
            shape = ifcopenshell.geom.create_shape(settings, product)
            vertices = shape.geometry.verts
            faces = shape.geometry.faces
            if not faces or len(faces) % 3:
                continue
            points = [
                transform.to_project_point_m(
                    tuple(float(vertices[index + axis]) * inspector.unit_scale_to_meters for axis in range(3))
                )
                for index in range(0, len(vertices), 3)
            ]
            triangles = []
            for index in range(0, len(faces), 3):
                tri_indices = [int(faces[index + axis]) for axis in range(3)]
                if any(vertex < 0 or vertex >= len(points) for vertex in tri_indices):
                    raise ValueError("invalid tessellation face index")
                triangles.append([points[vertex] for vertex in tri_indices])
            if not triangles:
                continue
            raw_name = " ".join(str(getattr(product, "Name", None) or product.is_a()).split())
            result.append({
                "name": f"{product.is_a()}: {raw_name}"[:80],
                "storey": storey_name,
                "ifc_global_id": guid,
                "ifc_type": str(product.is_a()),
                "triangles": triangles,
            })
        except Exception as exc:
            reason = " ".join(str(exc).split())[:180]
            skipped.append(f"{product.is_a()} {guid}: {reason}")
    if skipped:
        logger.warning("Could not tessellate %d IFC products for native geometry; first: %s", len(skipped), skipped[0])
    return result, skipped


def canonicalize_room_storey_assignments(
    room_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Move rooms to a unique level whose elevation matches their floor geometry.

    IFC spatial containment can be wrong even when an IfcSpace has usable geometry.
    Resolve those records before callers apply a selected-storey filter so a room
    assigned to a modeling-reference level is not silently omitted from its real level.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, room in enumerate(room_records):
        storey_name = str(room.get("source_storey") or "Unassigned").strip() or "Unassigned"
        grouped.setdefault(storey_name, []).append({**room, "__bridge_order": index})
    _reassign_misleveled_room_groups(grouped)
    canonical_records = [room for rooms in grouped.values() for room in rooms]
    canonical_records.sort(key=lambda room: int(room.pop("__bridge_order")))
    return canonical_records


def _reassign_misleveled_room_groups(grouped: dict[str, list[dict[str, Any]]]) -> None:
    group_levels: dict[str, tuple[float, float | None] | None] = {}
    for name, rooms in grouped.items():
        floors = [float(room["floor_z_m"]) for room in rooms]
        source_elevations = [
            float(room["source_storey_elevation_m"])
            for room in rooms
            if room.get("source_storey_elevation_m") is not None
        ]
        if not all(math.isfinite(value) for value in floors + source_elevations):
            group_levels[name] = None
            continue
        group_levels[name] = (
            statistics.median(floors),
            statistics.median(source_elevations) if source_elevations else None,
        )

    for name, rooms in list(grouped.items()):
        current = group_levels[name]
        if current is None:
            continue
        floor_elevation, source_elevation = current
        if source_elevation is None or abs(floor_elevation - source_elevation) <= 0.05:
            continue
        matches = [
            candidate
            for candidate, levels in group_levels.items()
            if candidate != name
            and levels is not None
            and levels[1] is not None
            and abs(levels[0] - levels[1]) <= 0.05
            and abs(levels[0] - floor_elevation) <= 0.02
        ]
        if len(matches) != 1:
            continue

        target = matches[0]
        target_source_elevation = group_levels[target][1]
        grouped[target].extend(
            {
                **room,
                "source_storey": target,
                "source_storey_elevation_m": target_source_elevation,
            }
            for room in rooms
        )
        del grouped[name]
        logger.warning(
            "Rooms assigned to IFC storey '%s' are at %.4f m, matching storey '%s' "
            "(%.4f m); placing them on that verified native level.",
            name,
            floor_elevation,
            target,
            target_source_elevation,
        )


def _ifc_site_info(inspector: IfcModelInspector) -> dict[str, Any]:
    location = "IFC import location"
    latitude = None
    longitude = None
    ifc_file = getattr(inspector, "ifc_file", None)
    if ifc_file is not None:
        sites = ifc_file.by_type("IfcSite")
        if sites:
            site = sites[0]
            location = str(getattr(site, "Name", None) or "").strip() or location
            latitude = _compound_angle_to_degrees(getattr(site, "RefLatitude", None), "latitude")
            longitude = _compound_angle_to_degrees(getattr(site, "RefLongitude", None), "longitude")
    return {
        "location": location,
        "latitude_degrees": latitude,
        "longitude_degrees": longitude,
    }


def _compound_angle_to_degrees(value: Any, label: str) -> float | None:
    if value is None:
        return None
    parts = [int(component) for component in value]
    if len(parts) != 4:
        raise ValueError(f"IFC site {label} must contain four DMS components.")
    if not 0 <= abs(parts[1]) < 60 or not 0 <= abs(parts[2]) < 60 or not 0 <= abs(parts[3]) < 1_000_000:
        raise ValueError(f"IFC site {label} contains invalid DMS components.")
    sign = -1 if next((part < 0 for part in parts if part != 0), False) else 1
    degrees, minutes, seconds, microseconds = (abs(part) for part in parts)
    result = sign * (degrees + minutes / 60 + (seconds + microseconds / 1_000_000) / 3600)
    limit = 90 if label == "latitude" else 180
    if not math.isfinite(result) or abs(result) > limit:
        raise ValueError(f"IFC site {label} is outside the valid geographic range.")
    return result


class DialuxNativeProjectExporter:
    """Runs the version-pinned native adapter and reload-verifies its .evo output."""

    def __init__(self, *, host_path: str | None = None, dialux_install: str | None = None) -> None:
        self.host_path = Path(host_path) if host_path else self._find_native_host()
        executable = find_dialux_executable()
        self.dialux_install = Path(dialux_install or (Path(executable).parent if executable else ""))

    def export(
        self,
        inspector: IfcModelInspector,
        room_records: list[dict[str, Any]],
        output_evo_path: str,
        *,
        coordinate_transform: CoordinateTransform | None = None,
        geometry_origin_m: tuple[float, float, float] | None = None,
        workplane_m: float = 0.85,
        include_native_geometry: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if not self.host_path.is_file():
            raise FileNotFoundError(
                "The native DIALux adapter is missing. Rebuild or reinstall DIALux IFC Bridge "
                "with its native helper."
            )
        if not self.dialux_install.is_dir() or not (self.dialux_install / "DIALux_x64.dll").is_file():
            raise FileNotFoundError(
                "A compatible DIALux evo installation was not found. The native project adapter "
                "uses the DIALux assemblies already installed on this computer."
            )
        output_path = Path(output_evo_path).resolve()
        if output_path.suffix.lower() != ".evo":
            raise ValueError("The native DIALux project output must use the .evo extension.")
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite an existing DIALux project: {output_path}")
        room_audit_path = output_path.with_name(output_path.stem + "_room_audit.json")
        if room_audit_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite an existing native room audit: {room_audit_path}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback(0.02, "Preparing native DIALux building and extracting IFC geometry...")
        plan = build_native_model_plan(
            inspector,
            room_records,
            coordinate_transform=coordinate_transform,
            geometry_origin_m=geometry_origin_m,
            workplane_m=workplane_m,
            include_native_geometry=include_native_geometry,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        token = uuid.uuid4().hex
        staged_project = output_path.with_name(f".{output_path.stem}.{token}.evo")
        staged_audit = room_audit_path.with_name(f".{room_audit_path.stem}.{token}.json")
        project_committed = False
        audit_committed = False
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Native DIALux project creation was cancelled.")

            with tempfile.TemporaryDirectory(prefix="dialux-ifc-native-") as directory:
                input_path = Path(directory) / "native_model.json"
                input_path.write_text(json.dumps(plan, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                create_text = self._run_host(
                    ["create", str(input_path), str(staged_project), str(self.dialux_install)],
                    cancel_event,
                )
                create_readback = self._read_json_result(create_text)
                if progress_callback:
                    progress_callback(0.7, "Reload-verifying the saved DIALux project...")
                readback_text = self._run_host(
                    ["inspect", str(staged_project), str(self.dialux_install)],
                    cancel_event,
                )

            readback = self._read_json_result(readback_text)
            storeys = self._verify_readback(plan, readback, create_readback=create_readback)
            self._write_room_audit(staged_audit, inspector, output_path, plan, storeys)

            if output_path.exists() or room_audit_path.exists():
                raise FileExistsError("The native project or room audit path was created by another process.")
            os.replace(staged_project, output_path)
            project_committed = True
            os.replace(staged_audit, room_audit_path)
            audit_committed = True

            room_count = sum(len(storey["rooms"]) for storey in storeys)
            logger.info(
                "Created native DIALux project %s with %d storeys and %d rooms",
                output_path,
                len(storeys),
                room_count,
            )
            if progress_callback:
                progress_callback(1.0, "Native DIALux project created and verified.")
            return {
                "project_path": str(output_path),
                "storey_count": len(storeys),
                "room_count": room_count,
                "storeys": storeys,
                "site": plan["site"],
                "readback": readback,
                "native_counts": readback.get("native_counts", {}),
                "room_audit_path": str(room_audit_path),
                "geometry_warnings": plan["geometry_warnings"],
            }
        except Exception:
            if project_committed and output_path.exists():
                output_path.unlink()
            if audit_committed and room_audit_path.exists():
                room_audit_path.unlink()
            raise
        finally:
            for temporary_path in (staged_project, staged_audit):
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove incomplete native export artifact %s", temporary_path)

    @staticmethod
    def _write_room_audit(
        audit_path: Path,
        inspector: IfcModelInspector,
        project_path: Path,
        plan: dict[str, Any],
        verified_storeys: list[dict[str, Any]],
    ) -> None:
        rooms = []
        for storey in plan["storeys"]:
            for room in storey["rooms"]:
                rooms.append(
                    {
                        "ifc_global_id": room["ifc_global_id"],
                        "source_name": room["source_name"],
                        "source_ifc_storey": room["source_ifc_storey"],
                        "native_storey": storey["name"],
                        "native_name": room["name"],
                        "source_floor_z_m": room["floor_z_m"],
                        "height_m": room["height_m"],
                        "geometry_diagnostics": room["geometry_diagnostics"],
                        "native_contour_xy_m": room["contour"],
                    }
                )
        audit = {
            "format": "DIALux IFC Bridge native room audit",
            "format_version": 1,
            "source_file": inspector.file_path,
            "source_schema": inspector.schema,
            "native_project": str(project_path),
            "coordinate_transform": plan["coordinate_transform"],
            "verified_storeys": verified_storeys,
            "native_geometry_counts": {
                "room_count": sum(len(storey.get("rooms", [])) for storey in verified_storeys),
                "ifc_mesh_element_count": len(plan.get("native_elements", [])),
                "ifc_mesh_triangle_count": sum(
                    len(element["triangles"]) for element in plan.get("native_elements", [])
                ),
                "ifc_mesh_global_ids": [element["ifc_global_id"] for element in plan.get("native_elements", [])],
                "native_meshes": [
                    {
                        "ifc_global_id": element["ifc_global_id"],
                        "ifc_type": element["ifc_type"],
                        "native_name": element["name"],
                        "native_storey": element["storey"],
                        "triangle_count": len(element["triangles"]),
                    }
                    for element in plan.get("native_elements", [])
                ],
                "boundary_element_count": sum(
                    len(storey.get("storey_elements", [])) for storey in verified_storeys
                ),
                "boundary_contour_count": sum(
                    int(element.get("contour_count", 0))
                    for storey in verified_storeys
                    for element in storey.get("storey_elements", [])
                ),
                "boundary_associated_space_count": sum(
                    int(element.get("associated_space_count", 0))
                    for storey in verified_storeys
                    for element in storey.get("storey_elements", [])
                ),
            },
            "geometry_warnings": plan["geometry_warnings"],
            "native_geometry_warnings": plan.get("native_geometry_warnings", []),
            "rooms": rooms,
        }
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=audit_path.parent,
                prefix=audit_path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = output.name
                json.dump(audit, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, audit_path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def open_project(project_path: str) -> None:
        executable = find_dialux_executable()
        if not executable:
            raise FileNotFoundError("DIALux evo is not installed or its executable could not be located.")
        if not Path(project_path).is_file():
            raise FileNotFoundError(f"The native DIALux project does not exist: {project_path}")
        subprocess.Popen([executable, str(Path(project_path).resolve())], shell=False)

    @staticmethod
    def _find_native_host() -> Path:
        roots = [Path(sys.executable).resolve().parent]
        if getattr(sys, "frozen", False):
            roots.append(Path(getattr(sys, "_MEIPASS", roots[0])))
        project_root = Path(__file__).resolve().parents[1]
        roots.extend(
            [
                project_root,
                project_root / "build" / "nativehost",
                project_root / "dist" / "DialuxIFCBridge",
                project_root / "native" / "bin" / "Release" / "net8.0-windows",
                project_root / "native" / "bin" / "Release" / "net8.0-windows" / "win-x64",
            ]
        )
        candidates: list[Path] = []
        for root in roots:
            candidate = root / "native" / NATIVE_HOST_NAME
            if candidate.is_file():
                candidates.append(candidate)
            candidate = root / NATIVE_HOST_NAME
            if candidate.is_file():
                candidates.append(candidate)
        for candidate in candidates:
            if DialuxNativeProjectExporter._is_self_contained_native_host(candidate):
                return candidate
        if candidates:
            raise RuntimeError(
                "The installed native DIALux adapter requires a separate .NET runtime. "
                "Rebuild it with the self-contained Windows publish settings."
            )
        return roots[0] / "native" / NATIVE_HOST_NAME

    @staticmethod
    def _is_self_contained_native_host(host_path: Path) -> bool:
        runtime_config = host_path.with_name("DialuxIfcNativeHost.runtimeconfig.json")
        try:
            runtime_options = json.loads(runtime_config.read_text(encoding="utf-8"))["runtimeOptions"]
        except (OSError, KeyError, json.JSONDecodeError):
            return False
        return bool(runtime_options.get("includedFrameworks")) and all(
            (host_path.parent / name).is_file()
            for name in ("coreclr.dll", "hostfxr.dll", "hostpolicy.dll")
        )

    def _run_host(self, arguments: list[str], cancel_event: threading.Event | None) -> str:
        command = [str(self.host_path), *arguments]
        log_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False) as log:
                log_path = log.name
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                process = subprocess.Popen(
                    command,
                    cwd=str(self.dialux_install),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creation_flags,
                )
                deadline = time.monotonic() + 900
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise InterruptedError("Native DIALux project creation was cancelled.")
                    if time.monotonic() >= deadline:
                        process.kill()
                        process.wait()
                        raise TimeoutError("The native DIALux adapter timed out after 15 minutes.")
                    time.sleep(0.1)
                log.flush()
                log.seek(0)
                output = log.read()
            if process.returncode:
                detail = output.strip() or f"Native DIALux adapter exited with code {process.returncode}."
                raise RuntimeError(f"Native DIALux project operation failed: {detail}")
            return output
        finally:
            if log_path:
                try:
                    os.unlink(log_path)
                except OSError:
                    logger.warning("Could not remove native adapter log %s", log_path, exc_info=True)

    @staticmethod
    def _read_json_result(output: str) -> dict[str, Any]:
        for line in reversed(output.splitlines()):
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                return result
        raise RuntimeError("The native DIALux adapter returned no project readback.")

    @staticmethod
    def _verify_readback(
        plan: dict[str, Any],
        readback: dict[str, Any],
        *,
        create_readback: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(readback.get("location"), str) or not readback["location"].strip():
            raise RuntimeError("The saved DIALux project has no site location for Construction mode.")
        expected_site = plan["site"]
        if readback.get("location") != expected_site["location"]:
            raise RuntimeError("The saved DIALux project did not preserve the IFC site location label.")
        for field in ("latitude_degrees", "longitude_degrees"):
            expected_value = expected_site[field]
            if expected_value is not None and abs(float(readback[field]) - expected_value) > 1e-7:
                raise RuntimeError(f"The saved DIALux project did not preserve the IFC site {field}.")
        expected = {storey["name"]: storey for storey in plan["storeys"]}
        actual = [
            storey
            for building in readback.get("buildings", [])
            for storey in building.get("storeys", [])
        ]
        if len(actual) != len(expected):
            raise RuntimeError(
                f"The saved DIALux project contains {len(actual)} storeys; "
                f"{len(expected)} were requested."
            )
        by_name = {storey.get("name"): storey for storey in actual}
        for name, storey in expected.items():
            saved = by_name.get(name)
            if saved is None:
                raise RuntimeError(f"The saved DIALux project is missing storey '{name}'.")
            if abs(float(saved["elevation_m"]) - storey["elevation_m"]) > 0.005:
                raise RuntimeError(
                    f"Storey '{name}' reloaded at {saved['elevation_m']:.4f} m instead of "
                    f"{storey['elevation_m']:.4f} m."
                )
            actual_room_count = len(saved.get("rooms", []))
            expected_room_count = len(storey["rooms"])
            if actual_room_count != expected_room_count:
                raise RuntimeError(
                    f"Storey '{name}' reloaded with {actual_room_count} rooms; "
                    f"{expected_room_count} were requested."
                )
            if "storey_elements" in saved:
                boundary_contours = sum(
                    int(element.get("contour_count", 0))
                    for element in saved["storey_elements"]
                )
                boundary_spaces = sum(
                    int(element.get("associated_space_count", 0))
                    for element in saved["storey_elements"]
                )
                if boundary_contours < expected_room_count or boundary_spaces != expected_room_count:
                    raise RuntimeError(
                        f"Storey '{name}' reloaded {boundary_contours} native room-boundary contours "
                        f"associated with {boundary_spaces} spaces; expected at least "
                        f"{expected_room_count} contours and exactly {expected_room_count} spaces."
                    )
            expected_mesh_count = sum(1 for element in plan.get("native_elements", []) if element["storey"] == name)
            actual_mesh_count = sum(
                1 for element in saved.get("contained_elements", [])
                if element.get("is_generic_geometry") is True
            )
            if actual_mesh_count != expected_mesh_count:
                raise RuntimeError(
                    f"Storey '{name}' reloaded {actual_mesh_count} native IFC mesh elements; "
                    f"{expected_mesh_count} were requested. Create-time readback reports "
                    f"{(create_readback or {}).get('native_counts', {}).get('generic_geometry_element_count', 'unknown')} "
                    "generic geometry elements."
                )
            room_elevations = saved.get("room_floor_elevations_m")
            if room_elevations is not None and any(
                abs(float(room_elevation) - storey["elevation_m"]) > 0.005
                for room_elevation in room_elevations
            ):
                raise RuntimeError(
                    f"Rooms on storey '{name}' did not reload at the storey elevation; "
                    "the native room geometry may not align with the exported OBJ."
                )
            saved["source_elevation_m"] = storey["source_elevation_m"]
            saved["elevation_basis"] = storey["elevation_basis"]
        return actual
