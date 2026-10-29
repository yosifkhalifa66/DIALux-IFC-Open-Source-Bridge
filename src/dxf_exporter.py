"""Minimal ASCII DXF underlay export from the indexed IFC geometry."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable

import ifcopenshell.geom

from .coordinate_transform import CoordinateTransform
from .ifc_parser import IfcModelInspector
from .utils import logger, sanitize_filename


class DialuxDxfExporter:
    def __init__(self, inspector: IfcModelInspector) -> None:
        self.inspector = inspector

    def export(
        self,
        output_dxf_path: str,
        selected_categories: list[str] | None = None,
        selected_storeys: list[str] | None = None,
        target_unit: str = "metres",
        scale_factor: float = 1.0,
        coordinate_transform: CoordinateTransform | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        from .obj_exporter import UNIT_PER_METER

        if self.inspector.ifc_file is None:
            raise RuntimeError("Load an IFC model before exporting.")
        if target_unit not in UNIT_PER_METER:
            raise ValueError(f"Unsupported output unit: {target_unit}")
        if scale_factor <= 0:
            raise ValueError("The scale multiplier must be positive.")
        output_path = os.path.abspath(output_dxf_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        categories = set(selected_categories) if selected_categories is not None else None
        storeys = set(selected_storeys) if selected_storeys is not None else None
        elements = []
        for ifc_class, products in self.inspector.elements_by_class.items():
            if ifc_class in {"IfcSpace", "IfcZone"}:
                continue
            if categories is not None and ifc_class not in categories:
                continue
            for product in products:
                guid = str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
                storey = self.inspector.element_to_storey.get(guid, "Unassigned")
                if storeys is None or storey in storeys:
                    elements.append((ifc_class, storey, product))
        if not elements:
            raise ValueError("No elements match the selected categories and storeys.")

        if coordinate_transform is None:
            coordinate_transform = CoordinateTransform(
                source_unit_to_meters=self.inspector.unit_scale_to_meters,
                output_units_per_meter=UNIT_PER_METER[target_unit],
                scale_factor=scale_factor,
            )
        else:
            coordinate_transform.require_compatible_export(
                source_unit_to_meters=self.inspector.unit_scale_to_meters,
                output_units_per_meter=UNIT_PER_METER[target_unit],
                scale_factor=scale_factor,
            )
        temp_path = output_path + ".tmp"
        face_count = 0
        settings = self.inspector.get_tessellation_settings()
        try:
            with open(temp_path, "w", encoding="ascii", newline="\n") as dxf:
                insunits = {"metres": 6, "millimetres": 4, "feet": 2, "inches": 1}[target_unit]
                dxf.write(f"0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n{insunits}\n0\nENDSEC\n")
                dxf.write("0\nSECTION\n2\nENTITIES\n")
                for index, (ifc_class, storey, element) in enumerate(elements):
                    if cancel_event is not None and cancel_event.is_set():
                        raise InterruptedError("DXF export was cancelled.")
                    if progress_callback:
                        progress_callback((index + 1) / len(elements), f"DXF mesh {index + 1}/{len(elements)}")
                    try:
                        geometry = ifcopenshell.geom.create_shape(settings, element).geometry
                        vertices, faces = geometry.verts, geometry.faces
                    except Exception as exc:
                        logger.debug("Could not tessellate DXF element %s: %s", getattr(element, "GlobalId", ""), exc)
                        continue
                    layer = sanitize_filename(f"{storey}_{ifc_class}").replace(" ", "_")[:31]
                    for face_index in range(0, len(faces) - 2, 3):
                        points = []
                        for offset in range(3):
                            vertex = int(faces[face_index + offset]) * 3
                            points.append(
                                coordinate_transform.to_output_point(
                                    tuple(float(vertices[vertex + axis]) for axis in range(3))
                                )
                            )
                        points.append(points[-1])
                        dxf.write(f"0\n3DFACE\n8\n{layer}\n")
                        for point_index, (x, y, z) in enumerate(points):
                            dxf.write(
                                f"{10 + point_index}\n{x:.12g}\n"
                                f"{20 + point_index}\n{y:.12g}\n"
                                f"{30 + point_index}\n{z:.12g}\n"
                            )
                        face_count += 1
                dxf.write("0\nENDSEC\n0\nEOF\n")
            if face_count == 0:
                raise ValueError("No usable 3D geometry was produced for DXF.")
            os.replace(temp_path, output_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        if progress_callback:
            progress_callback(1.0, "DXF export complete.")
        return {
            "dxf_path": output_path,
            "total_faces": face_count,
            "output_unit": target_unit,
            "origin_offset_m": list(coordinate_transform.origin_offset_m),
            "rotation_radians": coordinate_transform.rotation_radians,
        }
