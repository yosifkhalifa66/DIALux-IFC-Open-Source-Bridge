"""Semantic OBJ/MTL export with explicit unit conversion and IFC sidecars."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
import threading
import time
from typing import Any, Callable

import ifcopenshell.geom
import ifcopenshell.util.element

from .coordinate_transform import CoordinateTransform
from .ifc_parser import IfcModelInspector
from .utils import APP_VERSION, DEFAULT_MATERIALS, logger, sanitize_filename

ProgressCallback = Callable[[float, str], None]
UNIT_PER_METER = {"metres": 1.0, "millimetres": 1000.0, "feet": 3.280839895013123, "inches": 39.37007874015748}


class DialuxObjExporter:
    """Writes DIALux-friendly geometry and a separate, lossless IFC data index."""

    def __init__(self, inspector: IfcModelInspector) -> None:
        self.inspector = inspector

    def export(
        self,
        output_obj_path: str,
        selected_categories: list[str] | None = None,
        selected_storeys: list[str] | None = None,
        target_unit: str = "metres",
        scale_factor: float = 1.0,
        group_by: str = "storey_and_category",
        include_spaces: bool = False,
        include_curtain_walls: bool = True,
        preserve_names: bool = True,
        rebase_origin: bool = True,
        coordinate_transform: CoordinateTransform | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if self.inspector.ifc_file is None:
            raise RuntimeError("Load an IFC model before exporting.")
        if target_unit not in UNIT_PER_METER:
            raise ValueError(f"Unsupported output unit: {target_unit}")
        if not math.isfinite(scale_factor) or scale_factor <= 0:
            raise ValueError("The scale multiplier must be a positive finite number.")
        if group_by not in {"storey_and_category", "category", "storey"}:
            raise ValueError(f"Unsupported grouping mode: {group_by}")

        obj_path = os.path.abspath(output_obj_path)
        output_dir = os.path.dirname(obj_path)
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(obj_path))[0]
        mtl_path = os.path.join(output_dir, base_name + ".mtl")
        metadata_path = os.path.join(output_dir, base_name + "_metadata.json")
        rooms_path = os.path.join(output_dir, base_name + "_rooms.csv")

        elements = self._select_elements(
            selected_categories,
            selected_storeys,
            include_spaces,
            include_curtain_walls,
        )
        if not elements:
            raise ValueError("No elements match the selected categories and storeys.")

        output_scale = self.inspector.unit_scale_to_meters * UNIT_PER_METER[target_unit] * scale_factor
        if not math.isfinite(output_scale) or output_scale <= 0:
            raise ValueError("The resulting unit scale is invalid.")
        if coordinate_transform is not None:
            coordinate_transform.require_compatible_export(
                source_unit_to_meters=self.inspector.unit_scale_to_meters,
                output_units_per_meter=UNIT_PER_METER[target_unit],
                scale_factor=scale_factor,
            )

        stage_dir = tempfile.mkdtemp(prefix=".dialux-export-", dir=output_dir)
        staged = {
            obj_path: os.path.join(stage_dir, base_name + ".obj"),
            mtl_path: os.path.join(stage_dir, base_name + ".mtl"),
            metadata_path: os.path.join(stage_dir, base_name + "_metadata.json"),
            rooms_path: os.path.join(stage_dir, base_name + "_rooms.csv"),
        }
        start = time.monotonic()
        material_defs: dict[str, dict[str, Any]] = {}
        metadata_elements: list[dict[str, Any]] = []
        selected_storey_names = set(selected_storeys) if selected_storeys is not None else None
        selected_rooms = [
            room
            for room in self.inspector.rooms
            if selected_storey_names is None or room["storey"] in selected_storey_names
        ]
        room_ids = {room["id"] for room in selected_rooms}
        room_metadata = []
        for space in self.inspector.ifc_file.by_type("IfcSpace"):
            guid = str(getattr(space, "GlobalId", "") or f"step-{space.id()}")
            if guid in room_ids:
                room_metadata.append(
                    self._element_metadata(
                        space,
                        "IfcSpace",
                        self.inspector.element_to_storey.get(guid, "Unassigned"),
                    )
                )
        origin_m: tuple[float, float, float] | None = (
            coordinate_transform.origin_offset_m if coordinate_transform is not None else None
        )
        transform = coordinate_transform
        vertex_offset = 1
        vertex_count = 0
        face_count = 0
        skipped_count = 0
        geometry_min: list[float] | None = None
        geometry_max: list[float] | None = None

        try:
            settings = self.inspector.get_tessellation_settings()
            with open(staged[obj_path], "w", encoding="utf-8", newline="\n") as obj:
                obj.write(f"# DIALux IFC Bridge {APP_VERSION} - geometry in {target_unit}\n")
                obj.write("# IFC length unit: " + self.inspector.length_unit + "\n")
                obj.write("# Coordinates are rebased to a local origin.\n" if rebase_origin else "# IFC world coordinates retained.\n")
                obj.write(f"mtllib {os.path.basename(mtl_path)}\n\n")

                for index, (ifc_class, storey_name, element) in enumerate(elements):
                    self._check_cancelled(cancel_event)
                    name = str(getattr(element, "Name", None) or ifc_class)
                    guid = str(getattr(element, "GlobalId", "") or f"step-{element.id()}")
                    ifc_material_name = self._ifc_material_name(element)
                    fallback_material = self._resolve_material(
                        element, ifc_class, ifc_material_name=ifc_material_name
                    )
                    metadata_elements.append(self._element_metadata(element, ifc_class, storey_name))
                    if ifc_class == "IfcZone":
                        skipped_count += 1
                        continue
                    self._report(
                        progress_callback,
                        (index + 1) / len(elements),
                        f"Meshing {index + 1:,}/{len(elements):,}: {name}",
                    )

                    try:
                        shape = ifcopenshell.geom.create_shape(settings, element)
                        vertices = shape.geometry.verts
                        faces = shape.geometry.faces
                    except Exception as exc:
                        skipped_count += 1
                        logger.debug("Could not tessellate %s (%s): %s", name, guid, exc)
                        continue

                    if len(vertices) < 9 or len(faces) < 3 or len(vertices) % 3 or len(faces) % 3:
                        skipped_count += 1
                        continue
                    if transform is None:
                        if rebase_origin:
                            origin_m = tuple(
                                float(vertices[axis]) * self.inspector.unit_scale_to_meters
                                for axis in range(3)
                            )
                        else:
                            origin_m = (0.0, 0.0, 0.0)
                        transform = CoordinateTransform(
                            source_unit_to_meters=self.inspector.unit_scale_to_meters,
                            origin_offset_m=origin_m,
                            output_units_per_meter=UNIT_PER_METER[target_unit],
                            scale_factor=scale_factor,
                            origin_basis=(
                                "first_exported_geometry_vertex"
                                if rebase_origin
                                else "world_origin"
                            ),
                        )

                    safe_name = sanitize_filename(name if preserve_names else guid or ifc_class).replace(" ", "_")
                    safe_storey = sanitize_filename(storey_name).replace(" ", "_")
                    safe_class = sanitize_filename(ifc_class).replace(" ", "_")
                    if group_by == "storey_and_category":
                        obj.write(f"g {safe_storey}_{safe_class}\n")
                    elif group_by == "storey":
                        obj.write(f"g {safe_storey}\n")
                    else:
                        obj.write(f"g {safe_class}\n")
                    obj.write(f"o {safe_class}_{safe_name}_{guid[:8] or index}\n")
                    if rebase_origin and origin_m is None:
                        origin_m = tuple(
                            float(vertices[axis]) * self.inspector.unit_scale_to_meters for axis in range(3)
                        )

                    local_vertex_count = len(vertices) // 3
                    for vertex_index in range(0, len(vertices), 3):
                        coords = transform.to_output_point(
                            tuple(float(vertices[vertex_index + axis]) for axis in range(3))
                        )
                        if geometry_min is None:
                            geometry_min = list(coords)
                            geometry_max = list(coords)
                        else:
                            geometry_min = [
                                min(current, coordinate)
                                for current, coordinate in zip(geometry_min, coords)
                            ]
                            geometry_max = [
                                max(current, coordinate)
                                for current, coordinate in zip(geometry_max, coords)
                            ]
                        obj.write("v " + " ".join(f"{coordinate:.12g}" for coordinate in coords) + "\n")

                    local_face_count = len(faces) // 3
                    geometry_materials = getattr(shape.geometry, "materials", ()) or ()
                    material_ids = getattr(shape.geometry, "material_ids", ()) or ()
                    use_face_materials = len(material_ids) == local_face_count
                    previous_material: str | None = None
                    for face_index in range(0, len(faces), 3):
                        indices = [int(faces[face_index + offset]) for offset in range(3)]
                        if any(vertex < 0 or vertex >= local_vertex_count for vertex in indices):
                            raise ValueError(f"IFC geometry contains an invalid face index for {guid or name}.")
                        triangle_index = face_index // 3
                        style_index = int(material_ids[triangle_index]) if use_face_materials else -1
                        style = (
                            geometry_materials[style_index]
                            if 0 <= style_index < len(geometry_materials)
                            else None
                        )
                        material_name, material_def = (
                            self._resolve_material(
                                element,
                                ifc_class,
                                style=style,
                                ifc_material_name=ifc_material_name,
                            )
                            if style is not None
                            else fallback_material
                        )
                        material_defs[material_name] = material_def
                        if material_name != previous_material:
                            obj.write(f"usemtl {material_name}\n")
                            previous_material = material_name
                        obj.write("f " + " ".join(str(vertex + vertex_offset) for vertex in indices) + "\n")
                    vertex_offset += local_vertex_count
                    vertex_count += local_vertex_count
                    face_count += local_face_count
                    obj.write("\n")

            if face_count == 0:
                raise ValueError(
                    "No usable 3D geometry was produced. Check that the IFC contains represented elements."
                )

            self._write_mtl(staged[mtl_path], material_defs)
            metadata = {
                "format_version": 1,
                "application": "DIALux IFC Bridge",
                "application_version": APP_VERSION,
                "source_file": self.inspector.file_path,
                "project_name": self.inspector.project_name,
                "authoring_app": self.inspector.authoring_app,
                "ifc_schema": self.inspector.schema,
                "source_length_unit": self.inspector.length_unit,
                "source_to_meters": self.inspector.unit_scale_to_meters,
                "output_unit": target_unit,
                "additional_scale_multiplier": scale_factor,
                "coordinates_rebased": rebase_origin,
                "origin_offset_m": list(origin_m) if origin_m is not None else [0.0, 0.0, 0.0],
                "rotation_radians": transform.rotation_radians if transform is not None else 0.0,
                "coordinate_transform": transform.to_metadata() if transform is not None else None,
                "exported_elements": metadata_elements,
                "rooms": room_metadata,
                "space_boundaries": self.inspector.space_boundaries,
                "rooms_note": (
                    "Room semantics are preserved in this sidecar and the room schedule regardless of "
                    "whether IFC space volumes are included as OBJ meshes. DIALux evo's OBJ importer "
                    "does not create native DIALux room objects."
                ),
                "geometry": {
                    "vertices": vertex_count,
                    "triangles": face_count,
                    "elements_without_geometry": skipped_count,
                    "exported_element_count": len(metadata_elements),
                    "bounds_min": geometry_min,
                    "bounds_max": geometry_max,
                    "bounds_unit": target_unit,
                },
            }
            with open(staged[metadata_path], "w", encoding="utf-8", newline="\n") as sidecar:
                json.dump(metadata, sidecar, ensure_ascii=False, indent=2, default=self._json_default)
                sidecar.write("\n")
            self._write_rooms_csv(staged[rooms_path], room_ids)

            for destination, source in staged.items():
                os.replace(source, destination)
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

        elapsed = time.monotonic() - start
        self._report(progress_callback, 1.0, "Export complete.")
        logger.info(
            "Exported %d vertices and %d triangles from %d selected elements to %s in %.2fs",
            vertex_count,
            face_count,
            len(elements),
            obj_path,
            elapsed,
        )
        return {
            "obj_path": obj_path,
            "mtl_path": mtl_path,
            "metadata_path": metadata_path,
            "rooms_path": rooms_path,
            "total_vertices": vertex_count,
            "total_faces": face_count,
            "elements_without_geometry": skipped_count,
            "elapsed_seconds": elapsed,
            "source_to_meters": self.inspector.unit_scale_to_meters,
            "output_unit": target_unit,
            "effective_scale": output_scale,
            "origin_offset_m": list(origin_m) if origin_m is not None else [0.0, 0.0, 0.0],
            "coordinate_transform": transform,
            "geometry_bounds": {
                "min": geometry_min,
                "max": geometry_max,
                "unit": target_unit,
            },
            "source_file": self.inspector.file_path,
            "selected_categories": tuple(selected_categories) if selected_categories is not None else None,
            "selected_storeys": tuple(selected_storeys) if selected_storeys is not None else None,
        }

    def _select_elements(
        self,
        categories: list[str] | None,
        storeys: list[str] | None,
        include_spaces: bool,
        include_curtain_walls: bool,
    ) -> list[tuple[str, str, Any]]:
        selected = []
        category_filter = set(categories) if categories is not None else None
        storey_filter = set(storeys) if storeys is not None else None
        for ifc_class, products in self.inspector.elements_by_class.items():
            if category_filter is not None and ifc_class not in category_filter:
                continue
            if ifc_class in {"IfcSpace", "IfcZone"} and not include_spaces:
                continue
            if ifc_class == "IfcCurtainWall" and not include_curtain_walls:
                continue
            for element in products:
                guid = str(getattr(element, "GlobalId", "") or f"step-{element.id()}")
                storey = self.inspector.element_to_storey.get(guid, "Unassigned")
                if storey_filter is not None and storey not in storey_filter:
                    continue
                selected.append((ifc_class, storey, element))
        return selected

    def _resolve_material(
        self,
        element: Any,
        ifc_class: str,
        *,
        style: Any = None,
        ifc_material_name: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        key = ifc_class if ifc_class in DEFAULT_MATERIALS else "Default"
        for candidate in DEFAULT_MATERIALS:
            if candidate != "Default":
                try:
                    if element.is_a(candidate):
                        key = candidate
                        break
                except (AttributeError, RuntimeError):
                    continue
        defaults = DEFAULT_MATERIALS.get(key, DEFAULT_MATERIALS["Default"])
        definition = dict(defaults)
        source_name = ifc_material_name or str(defaults["name"])
        if style is None:
            return self._safe_material_name(source_name), definition

        style_name = str(getattr(style, "name", "") or "").strip()
        if not style_name or style_name.casefold() == ifc_class.casefold() or style_name.startswith("IfcSurfaceStyle"):
            style_name = source_name
        diffuse = self._style_rgb(style, "diffuse")
        specular = self._style_rgb(style, "specular")
        if diffuse is not None:
            definition["Kd"] = diffuse
        if specular is not None:
            definition["Ks"] = specular
        try:
            transparency = float(getattr(style, "transparency"))
            if math.isfinite(transparency):
                definition["d"] = 1.0 - min(1.0, max(0.0, transparency))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

        color_key = "".join(f"{round(channel * 255):02X}" for channel in definition["Kd"])
        opacity_key = f"{round(float(definition.get('d', 1.0)) * 100):02d}"
        material_name = self._safe_material_name(f"IFC_{style_name}_{color_key}_{opacity_key}")
        return material_name, definition

    @staticmethod
    def _safe_material_name(value: str) -> str:
        safe = sanitize_filename(str(value)).replace(" ", "_")
        return safe[:120] or "IFC_Material"

    @staticmethod
    def _style_rgb(style: Any, attribute: str) -> tuple[float, float, float] | None:
        try:
            color = getattr(style, attribute)
            if callable(color):
                color = color()
            components = getattr(color, "components", None)
            if callable(components):
                components = components()
            if components is None:
                components = tuple(getattr(color, channel) for channel in ("r", "g", "b"))
            values = tuple(float(component) for component in components)
            if len(values) != 3 or not all(math.isfinite(value) for value in values):
                return None
            return tuple(min(1.0, max(0.0, value)) for value in values)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None

    @staticmethod
    def _ifc_material_name(element: Any) -> str | None:
        try:
            materials = ifcopenshell.util.element.get_materials(element, should_inherit=True)
            names = [
                str(getattr(material, "Name", "") or "").strip()
                for material in materials
                if str(getattr(material, "Name", "") or "").strip()
            ]
            return " ".join(names) if names else None
        except Exception as exc:
            logger.debug("Could not read IFC materials for %s: %s", getattr(element, "GlobalId", ""), exc)
            return None

    def _element_metadata(self, element: Any, ifc_class: str, storey_name: str) -> dict[str, Any]:
        metadata = {
            "ifc_type": ifc_class,
            "global_id": getattr(element, "GlobalId", None),
            "name": getattr(element, "Name", None),
            "description": getattr(element, "Description", None),
            "object_type": getattr(element, "ObjectType", None),
            "tag": getattr(element, "Tag", None),
            "storey": storey_name,
        }
        try:
            metadata["property_sets"] = ifcopenshell.util.element.get_psets(element, should_inherit=True)
        except Exception as exc:
            logger.debug("Could not read property sets for %s: %s", metadata["global_id"], exc)
            metadata["property_sets"] = {}
        return metadata

    @staticmethod
    def _json_default(value: Any) -> Any:
        if hasattr(value, "wrappedValue"):
            return value.wrappedValue
        if hasattr(value, "is_a"):
            return {"ifc_type": value.is_a(), "step_id": value.id()}
        if isinstance(value, (set, tuple)):
            return list(value)
        return str(value)

    def _write_mtl(self, path: str, materials: dict[str, dict[str, Any]]) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as material_file:
            material_file.write("# DIALux IFC Bridge material library\n")
            for material_name, definition in materials.items():
                kd = definition.get("Kd", (0.65, 0.65, 0.65))
                ks = definition.get("Ks", (0.1, 0.1, 0.1))
                material_file.write(f"\n# {definition.get('desc', '')}\nnewmtl {material_name}\n")
                material_file.write("Ka 0.2 0.2 0.2\n")
                material_file.write(f"Kd {kd[0]:.4f} {kd[1]:.4f} {kd[2]:.4f}\n")
                material_file.write(f"Ks {ks[0]:.4f} {ks[1]:.4f} {ks[2]:.4f}\n")
                material_file.write(f"d {float(definition.get('d', 1.0)):.4f}\nillum 2\nNs 10\n")

    def _write_rooms_csv(self, path: str, room_ids: set[str]) -> None:
        boundaries: dict[str, int] = {}
        for boundary in self.inspector.space_boundaries:
            space_id = boundary.get("space_id")
            if space_id:
                boundaries[space_id] = boundaries.get(space_id, 0) + 1
        fields = ("global_id", "name", "long_name", "storey", "composition_type", "interior_or_exterior", "boundary_count")
        with open(path, "w", encoding="utf-8-sig", newline="") as rooms_file:
            writer = csv.DictWriter(rooms_file, fieldnames=fields)
            writer.writeheader()
            for room in self.inspector.rooms:
                if room["id"] not in room_ids:
                    continue
                writer.writerow(
                    {
                        "global_id": room["id"],
                        "name": room["name"],
                        "long_name": room.get("long_name") or "",
                        "storey": room["storey"],
                        "composition_type": room.get("composition_type") or "",
                        "interior_or_exterior": room.get("interior_or_exterior") or "",
                        "boundary_count": boundaries.get(room["id"], 0),
                    }
                )

    @staticmethod
    def _report(callback: ProgressCallback | None, fraction: float, text: str) -> None:
        if callback is not None:
            callback(fraction, text)

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("IFC export was cancelled.")
