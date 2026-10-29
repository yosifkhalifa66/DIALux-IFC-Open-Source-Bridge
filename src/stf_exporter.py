"""Export IFC space footprints as native DIALux evo STF room definitions."""

from __future__ import annotations

import json
import math
import os
import threading
import unicodedata
from datetime import date
from typing import Any, Callable

import ifcopenshell.geom
import ifcopenshell.util.placement
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .coordinate_transform import CoordinateTransform
from .ifc_parser import IfcModelInspector
from .utils import APP_VERSION, logger

ProgressCallback = Callable[[float, str], None]
MAX_STF_LABEL_LENGTH = 32


class DialuxStfExporter:
    """Converts represented IFC rooms into an STF import and provenance sidecar."""

    def __init__(
        self,
        inspector: IfcModelInspector,
        *,
        workplane_m: float = 0.85,
        maintenance_factor: float = 0.8,
        ceiling_reflectance: float = 0.7,
        wall_reflectance: float = 0.5,
        floor_reflectance: float = 0.2,
    ) -> None:
        self.inspector = inspector
        self.room_settings = {
            "workplane_m": workplane_m,
            "maintenance_factor": maintenance_factor,
            "ceiling_reflectance": ceiling_reflectance,
            "wall_reflectance": wall_reflectance,
            "floor_reflectance": floor_reflectance,
        }
        self._validate_room_settings()

    def export(
        self,
        output_stf_path: str,
        *,
        selected_storeys: list[str] | None = None,
        coordinate_transform: CoordinateTransform | None = None,
        geometry_origin_m: tuple[float, float, float] | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if self.inspector.ifc_file is None:
            raise RuntimeError("Load an IFC model before creating DIALux rooms.")
        if not output_stf_path.lower().endswith(".stf"):
            raise ValueError("Choose an .stf output file.")

        selected_spaces = self._selected_spaces(selected_storeys)
        selected_storey_names = sorted({storey for _, _, storey in selected_spaces})
        if len(selected_storey_names) > 1:
            raise ValueError(
                "STF cannot preserve IFC storey elevations. Export native STF rooms for one source "
                "storey at a time; use DIALux's native IFC import for a multi-storey building."
            )
        room_records = self._extract_room_records(selected_spaces, progress_callback, cancel_event)
        return self.export_room_records(
            output_stf_path,
            room_records,
            coordinate_transform=coordinate_transform,
            geometry_origin_m=geometry_origin_m,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def extract_rooms(
        self,
        *,
        selected_storeys: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[dict[str, Any]]:
        """Return validated IFC room contours in source coordinates, without writing files."""
        if self.inspector.ifc_file is None:
            raise RuntimeError("Load an IFC model before extracting DIALux rooms.")
        selected_spaces = self._selected_spaces(selected_storeys)
        room_records = self._extract_room_records(selected_spaces, progress_callback, cancel_event)
        self._report(progress_callback, 1.0, "IFC room contours extracted.")
        return room_records

    def export_room_records(
        self,
        output_stf_path: str,
        room_records: list[dict[str, Any]],
        *,
        selected_storeys: list[str] | None = None,
        coordinate_transform: CoordinateTransform | None = None,
        geometry_origin_m: tuple[float, float, float] | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Write STF from previously extracted records, so other exporters can reuse them."""
        if not output_stf_path.lower().endswith(".stf"):
            raise ValueError("Choose an .stf output file.")
        storey_filter = set(selected_storeys) if selected_storeys is not None else None
        selected_records = [
            {**room, "contour_m": list(room["contour_m"])}
            for room in room_records
            if storey_filter is None or room["source_storey"] in storey_filter
        ]
        if not selected_records:
            raise ValueError("The IFC contains no IfcSpace rooms in the selected storeys.")
        selected_storey_names = sorted({room["source_storey"] for room in selected_records})
        if len(selected_storey_names) > 1:
            raise ValueError(
                "STF cannot preserve IFC storey elevations. Export native STF rooms for one source "
                "storey at a time; use DIALux's native IFC import for a multi-storey building."
            )

        output_path = os.path.abspath(output_stf_path)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        sidecar_path = os.path.splitext(output_path)[0] + "_rooms.json"
        if coordinate_transform is not None and geometry_origin_m is not None:
            raise ValueError("Pass a coordinate transform or an origin offset, not both.")
        if coordinate_transform is None and geometry_origin_m is not None:
            coordinate_transform = CoordinateTransform(
                origin_offset_m=tuple(float(value) for value in geometry_origin_m)
            )
        self._align_to_geometry_origin(selected_records, coordinate_transform=coordinate_transform)
        lines, metadata = self._build_stf(selected_records)
        stf_data = ("\r\n".join(lines) + "\r\n").encode("latin-1", errors="strict")
        sidecar_data = (json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        self._check_cancelled(cancel_event)
        self._write_pair_atomically(output_path, sidecar_path, stf_data, sidecar_data)
        self._report(progress_callback, 1.0, "Native DIALux room file created.")
        logger.info("Wrote %d native room definitions to %s", len(selected_records), output_path)
        return {
            "stf_path": output_path,
            "metadata_path": sidecar_path,
            "room_count": len(selected_records),
            "storeys": sorted({room["source_storey"] for room in selected_records}),
            "manual_actions": metadata["manual_actions"],
        }

    def _selected_spaces(self, selected_storeys: list[str] | None) -> list[tuple[Any, str, str]]:
        model = self.inspector.ifc_file
        storey_filter = set(selected_storeys) if selected_storeys is not None else None
        selected_spaces = []
        for space in model.by_type("IfcSpace"):
            guid = self._guid(space)
            storey = self.inspector.element_to_storey.get(guid, "Unassigned")
            if storey_filter is None or storey in storey_filter:
                selected_spaces.append((space, guid, storey))
        if not selected_spaces:
            raise ValueError("The IFC contains no IfcSpace rooms in the selected storeys.")
        return selected_spaces

    def _extract_room_records(
        self,
        selected_spaces: list[tuple[Any, str, str]],
        progress_callback: ProgressCallback | None,
        cancel_event: threading.Event | None,
    ) -> list[dict[str, Any]]:
        settings = self.inspector.get_tessellation_settings()
        room_records: list[dict[str, Any]] = []
        room_count = len(selected_spaces)
        for index, (space, guid, storey) in enumerate(selected_spaces):
            self._check_cancelled(cancel_event)
            name = str(getattr(space, "LongName", None) or getattr(space, "Name", None) or f"Room {index + 1}")
            self._report(
                progress_callback,
                (index + 1) / (room_count + 1),
                f"Reading room {index + 1}/{room_count}: {name}",
            )
            try:
                geometry = ifcopenshell.geom.create_shape(settings, space).geometry
                vertices = geometry.verts
                faces = geometry.faces
            except Exception as exc:
                raise ValueError(
                    f"Room '{name}' has no usable IFC 3D representation. "
                    "Native DIALux room creation needs a closed footprint; this room cannot be drawn automatically."
                ) from exc
            if len(vertices) < 9 or len(faces) < 3 or len(vertices) % 3 or len(faces) % 3:
                raise ValueError(
                    f"Room '{name}' has incomplete 3D geometry and cannot be converted to a native DIALux room."
                )
            record = self._room_from_mesh(space, guid, storey, name, vertices, faces)
            room_records.append(record)

        self._validate_no_overlapping_room_footprints(room_records)
        return room_records

    def _room_from_mesh(
        self,
        space: Any,
        guid: str,
        storey: str,
        name: str,
        vertices: Any,
        faces: Any,
    ) -> dict[str, Any]:
        scale = self.inspector.unit_scale_to_meters
        xyz = [
            (
                float(vertices[index]) * scale,
                float(vertices[index + 1]) * scale,
                float(vertices[index + 2]) * scale,
            )
            for index in range(0, len(vertices), 3)
        ]
        if not all(math.isfinite(value) for vertex in xyz for value in vertex):
            raise ValueError(f"Room '{name}' contains a non-finite IFC coordinate.")
        z_values = [vertex[2] for vertex in xyz]
        z_min, z_max = min(z_values), max(z_values)
        height = z_max - z_min
        if height <= 0.05:
            raise ValueError(f"Room '{name}' is not a closed 3D space with a positive room height.")
        if self.room_settings["workplane_m"] >= height:
            raise ValueError(
                f"Room '{name}' is {height:.3f} m high, below the configured "
                f"{self.room_settings['workplane_m']:.3f} m workplane. Lower the workplane in Options."
            )
        footprint = self._ifc_footprint(space)
        storey_elevation = self._storey_elevation(storey)
        tolerance = max(1e-5, height * 1e-7)
        floor_triangles = []
        for index in range(0, len(faces) - 2, 3):
            indices = (int(faces[index]), int(faces[index + 1]), int(faces[index + 2]))
            if any(vertex < 0 or vertex >= len(xyz) for vertex in indices):
                raise ValueError(f"Room '{name}' contains an invalid triangle index.")
            triangle = [xyz[vertex] for vertex in indices]
            if all(abs(vertex[2] - z_min) <= tolerance for vertex in triangle):
                triangle_polygon = Polygon([(vertex[0], vertex[1]) for vertex in triangle])
                if triangle_polygon.is_valid and triangle_polygon.area > 1e-8:
                    floor_triangles.append(triangle_polygon)
        if not floor_triangles:
            if footprint is not None:
                contour, floor_z = footprint
                metadata = self._safe_properties(space)
                warnings = []
                if storey_elevation is not None and abs(floor_z - storey_elevation) > 0.05:
                    warning = (
                        f"Room '{name}' ({guid}) has no horizontal body floor; its IFC FootPrint "
                        f"elevation ({floor_z:.4f} m) disagrees with assigned storey '{storey}' "
                        f"({storey_elevation:.4f} m)."
                    )
                    warnings.append(warning)
                    logger.warning(warning)
                geometry_diagnostics = {
                    "selected_contour_source": "ifc_footprint",
                    "body_floor_z_m": z_min,
                    "ifc_footprint_floor_z_m": floor_z,
                    "ifc_footprint_area_m2": Polygon(contour).area,
                    "warnings": warnings,
                }
                return {
                    "ifc_global_id": guid,
                    "name": name,
                    "source_storey": storey,
                    "source_storey_elevation_m": storey_elevation,
                    "floor_z_m": floor_z,
                    "height_m": height,
                    "contour_m": contour,
                    "ifc_properties": metadata,
                    "source_offset_xy_m": [0.0, 0.0],
                    "geometry_diagnostics": geometry_diagnostics,
                }
            raise ValueError(
                f"Room '{name}' has no horizontal bottom surface in its IFC geometry. "
                "A floor outline cannot be inferred safely from its body or IFC FootPrint."
            )
        floor_shape = unary_union(floor_triangles)
        if floor_shape.geom_type != "Polygon":
            raise ValueError(
                f"Room '{name}' has a disconnected or ambiguous floor footprint "
                f"({floor_shape.geom_type}); it needs a simple closed outline."
            )
        if floor_shape.interiors:
            raise ValueError(f"Room '{name}' contains holes in its footprint, which native DIALux rooms cannot represent.")
        contour = [(float(x), float(y)) for x, y in list(floor_shape.exterior.coords)[:-1]]
        contour = self._simplify_contour(contour)
        if len(contour) < 3:
            raise ValueError(f"Room '{name}' has fewer than three usable floor-boundary points.")
        floor_z = z_min
        geometry_diagnostics = {
            "selected_contour_source": "body_floor_mesh",
            "body_floor_z_m": z_min,
            "ifc_footprint_floor_z_m": None,
            "body_floor_area_m2": floor_shape.area,
            "ifc_footprint_area_m2": None,
            "footprint_symmetric_difference_percent": None,
            "warnings": [],
        }
        if footprint is not None:
            footprint_contour, footprint_z = footprint
            footprint_shape = Polygon(footprint_contour)
            footprint_delta_percent = (
                floor_shape.symmetric_difference(footprint_shape).area
                / max(floor_shape.area, footprint_shape.area)
                * 100.0
            )
            geometry_diagnostics.update(
                {
                    "ifc_footprint_floor_z_m": footprint_z,
                    "ifc_footprint_area_m2": footprint_shape.area,
                    "footprint_symmetric_difference_percent": footprint_delta_percent,
                }
            )
            if footprint_delta_percent > 1.0:
                warning = (
                    f"Room '{name}' ({guid}) body-floor and IFC FootPrint outlines differ by "
                    f"{footprint_delta_percent:.2f}%; verify the room footprint before lighting use."
                )
                geometry_diagnostics["warnings"].append(warning)
                logger.warning(warning)
            mesh_matches_storey = (
                storey_elevation is not None and abs(floor_z - storey_elevation) <= 0.05
            )
            footprint_matches_storey = (
                storey_elevation is not None and abs(footprint_z - storey_elevation) <= 0.05
            )
            if footprint_matches_storey and not mesh_matches_storey:
                contour, floor_z = footprint_contour, footprint_z
                geometry_diagnostics["selected_contour_source"] = "ifc_footprint"
                logger.warning(
                    "Room '%s' body floor (%.4f m) disagrees with storey '%s' (%.4f m); "
                    "using its IFC FootPrint at %.4f m.",
                    name,
                    z_min,
                    storey,
                    storey_elevation,
                    footprint_z,
                )
            elif (
                storey_elevation is not None
                and not mesh_matches_storey
                and not footprint_matches_storey
            ):
                warning = (
                    f"Room '{name}' ({guid}) body floor ({z_min:.4f} m) and IFC FootPrint "
                    f"({footprint_z:.4f} m) both disagree with assigned storey '{storey}' "
                    f"({storey_elevation:.4f} m); retaining body-floor geometry pending review."
                )
                geometry_diagnostics["warnings"].append(warning)
                logger.warning(warning)

        metadata = self._safe_properties(space)
        return {
            "ifc_global_id": guid,
            "name": name,
            "source_storey": storey,
            "source_storey_elevation_m": storey_elevation,
            "floor_z_m": floor_z,
            "height_m": height,
            "contour_m": contour,
            "ifc_properties": metadata,
            "source_offset_xy_m": [0.0, 0.0],
            "geometry_diagnostics": geometry_diagnostics,
        }

    def _ifc_footprint(
        self, space: Any
    ) -> tuple[list[tuple[float, float]], float] | None:
        product_shape = getattr(space, "Representation", None)
        if product_shape is None:
            return None
        representations = [
            representation
            for representation in product_shape.Representations
            if str(representation.RepresentationIdentifier or "").casefold() == "footprint"
        ]
        if not representations:
            return None

        try:
            segments = []
            for representation in representations:
                for item in representation.Items:
                    if item.is_a("IfcPolyline"):
                        polylines = [item]
                    elif item.is_a("IfcGeometricCurveSet"):
                        polylines = [
                            curve for curve in item.Elements if curve.is_a("IfcPolyline")
                        ]
                        if len(polylines) != len(item.Elements):
                            return None
                    else:
                        return None
                    for polyline in polylines:
                        points = []
                        for point in polyline.Points:
                            coordinates = tuple(float(value) for value in point.Coordinates)
                            if len(coordinates) not in (2, 3):
                                return None
                            local = (*coordinates, 0.0) if len(coordinates) == 2 else coordinates
                            points.append(self._transform_footprint_point(space, local))
                        points = self._remove_duplicate_footprint_points(points)
                        if len(points) >= 2:
                            segments.append(points)

            points = self._stitch_footprint_segments(segments)
            if points is None or len(points) < 4:
                return None
            if math.dist(points[0], points[-1]) > 1e-4:
                return None
            if max(point[2] for point in points) - min(point[2] for point in points) > 0.01:
                return None
            floor_z = sum(point[2] for point in points[:-1]) / (len(points) - 1)
            contour = self._simplify_contour([(point[0], point[1]) for point in points[:-1]])
            polygon = Polygon(contour)
            if not polygon.is_valid or polygon.area <= 1e-8 or polygon.interiors:
                return None
            return contour, floor_z
        except (AttributeError, IndexError, TypeError, ValueError, RuntimeError):
            logger.debug(
                "Could not read IFC FootPrint representation for room %s; falling back to its 3D body.",
                getattr(space, "GlobalId", None) or space.id(),
                exc_info=True,
            )
            return None

    def _transform_footprint_point(
        self, space: Any, coordinates: tuple[float, ...]
    ) -> tuple[float, float, float]:
        placement = getattr(space, "ObjectPlacement", None)
        if placement is None:
            world = coordinates
        else:
            matrix = ifcopenshell.util.placement.get_local_placement(placement)
            world = tuple(
                sum(float(matrix[row][column]) * coordinates[column] for column in range(3))
                + float(matrix[row][3])
                for row in range(3)
            )
        scale = self.inspector.unit_scale_to_meters
        return tuple(value * scale for value in world)

    @staticmethod
    def _remove_duplicate_footprint_points(
        points: list[tuple[float, float, float]],
    ) -> list[tuple[float, float, float]]:
        result = []
        for point in points:
            if not result or math.dist(result[-1], point) > 1e-5:
                result.append(point)
        return result

    @staticmethod
    def _stitch_footprint_segments(
        segments: list[list[tuple[float, float, float]]],
    ) -> list[tuple[float, float, float]] | None:
        if not segments:
            return None
        remaining = list(segments)
        points = remaining.pop(0)
        while remaining and math.dist(points[-1], points[0]) > 1e-4:
            for index, segment in enumerate(remaining):
                if math.dist(points[-1], segment[0]) <= 1e-4:
                    points.extend(segment[1:])
                elif math.dist(points[-1], segment[-1]) <= 1e-4:
                    points.extend(reversed(segment[:-1]))
                else:
                    continue
                remaining.pop(index)
                break
            else:
                return None
        if remaining:
            return None
        if math.dist(points[-1], points[0]) <= 1e-4:
            points[-1] = points[0]
            return points
        return None

    @staticmethod
    def _simplify_contour(contour: list[tuple[float, float]]) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        for point in contour:
            if not result or math.dist(result[-1], point) > 1e-5:
                result.append(point)
        if len(result) > 3 and math.dist(result[0], result[-1]) <= 1e-5:
            result.pop()
        if len(result) > 512:
            raise ValueError(
                f"Room floor outline has {len(result)} points; simplify the contour below 512 points and retry."
            )
        if len(result) < 3 or not Polygon(result).is_valid:
            raise ValueError("A room footprint is invalid or self-intersecting.")
        signed_area = sum(
            result[index][0] * result[(index + 1) % len(result)][1]
            - result[(index + 1) % len(result)][0] * result[index][1]
            for index in range(len(result))
        )
        if signed_area < 0:
            result.reverse()
        return result

    @staticmethod
    def _guid(entity: Any) -> str:
        return str(getattr(entity, "GlobalId", "") or f"step-{entity.id()}")

    def _storey_elevation(self, name: str) -> float | None:
        for storey in self.inspector.storeys:
            if storey["name"] == name:
                elevation_known = storey.get(
                    "elevation_defined",
                    storey.get("elevation_raw") is not None or "elevation" in storey,
                )
                if not elevation_known:
                    return None
                return float(storey["elevation"])
        return None

    @staticmethod
    def _safe_properties(space: Any) -> dict[str, Any]:
        try:
            import ifcopenshell.util.element

            return ifcopenshell.util.element.get_psets(space, should_inherit=True)
        except Exception as exc:
            logger.debug("Could not read room property sets for %s: %s", getattr(space, "GlobalId", ""), exc)
            return {}

    @staticmethod
    def _validate_no_overlapping_room_footprints(rooms: list[dict[str, Any]]) -> None:
        by_storey: dict[str, list[dict[str, Any]]] = {}
        for room in rooms:
            by_storey.setdefault(room["source_storey"], []).append(room)

        overlaps: list[str] = []
        for storey, storey_rooms in by_storey.items():
            polygons = [Polygon(room["contour_m"]) for room in storey_rooms]
            tree = STRtree(polygons)
            for index, polygon in enumerate(polygons):
                for candidate in tree.query(polygon):
                    other_index = int(candidate)
                    if other_index <= index:
                        continue
                    other = polygons[other_index]
                    overlap_area = polygon.intersection(other).area
                    tolerance = max(1e-4, min(polygon.area, other.area) * 1e-6)
                    if overlap_area > tolerance:
                        overlaps.append(
                            f"'{storey_rooms[index]['name']}' and "
                            f"'{storey_rooms[other_index]['name']}' ({overlap_area:.3f} m²)"
                        )
                        if len(overlaps) == 5:
                            break
                if len(overlaps) == 5:
                    break
            if len(overlaps) == 5:
                break

        if overlaps:
            examples = "; ".join(overlaps)
            raise ValueError(
                "The IFC contains overlapping room footprints on the same storey: "
                f"{examples}. Overlapping native room spaces can produce an invalid building model. "
                "Correct the room boundaries in the IFC and export again."
            )

    def _align_to_geometry_origin(
        self,
        rooms: list[dict[str, Any]],
        coordinate_transform: CoordinateTransform | None = None,
    ) -> None:
        if coordinate_transform is None:
            origin_x = min(point[0] for room in rooms for point in room["contour_m"])
            origin_y = min(point[1] for room in rooms for point in room["contour_m"])
            coordinate_transform = CoordinateTransform(
                origin_offset_m=(origin_x, origin_y, 0.0)
            )
        for room in rooms:
            room["contour_m"] = [
                coordinate_transform.to_project_xy((x, y))
                for x, y in room["contour_m"]
            ]
            room["source_offset_xy_m"] = list(coordinate_transform.origin_offset_m[:2])
            room["storey_layout_offset_x_m"] = 0.0
            room["contour_m_stf"] = list(room["contour_m"])

    def _build_stf(self, rooms: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
        project_name = self._safe_stf_label(self.inspector.project_name or "IFC Building")
        author = "DIALux IFC Bridge"
        lines = [
            "[VERSION]",
            "STFF=1.0.5",
            "Progname=DialuxIFCBridge",
            "Progvers=" + APP_VERSION,
            "",
            "[Project]",
            "Name=" + project_name,
            "Date=" + date.today().isoformat(),
            "Operator=" + author,
            "NrRooms=" + str(len(rooms)),
        ]
        for index in range(len(rooms)):
            lines.append(f"Room{index + 1}=ROOM.R{index + 1}")

        names: set[str] = set()
        for index, room in enumerate(rooms, start=1):
            name = room["name"]
            if len({item["source_storey"] for item in rooms}) > 1:
                name = f"{name} ({room['source_storey']})"
            base_name = self._safe_stf_label(name)
            name = base_name
            suffix = self._safe_stf_label(str(room["ifc_global_id"]))[:8] or str(index)
            collision_index = 0
            while name.casefold() in names:
                unique_suffix = suffix if collision_index == 0 else f"{suffix}-{index}-{collision_index}"
                name = self._safe_stf_label(
                    base_name[: MAX_STF_LABEL_LENGTH - len(unique_suffix) - 1] + "-" + unique_suffix
                )
                collision_index += 1
            names.add(name.casefold())

            contour = room["contour_m_stf"]
            lines.extend(
                [
                    "",
                    f"[ROOM.R{index}]",
                    "Name=" + name,
                    "Height=" + self._number(room["height_m"]),
                    "WorkingPlane=" + self._number(self.room_settings["workplane_m"]),
                    "MF=" + self._number(self.room_settings["maintenance_factor"]),
                    "R_Ceiling=" + self._number(self.room_settings["ceiling_reflectance"]),
                    "R_Floor=" + self._number(self.room_settings["floor_reflectance"]),
                    "NrPoints=" + str(len(contour)),
                ]
            )
            for point_index, (x, y) in enumerate(contour, start=1):
                lines.append(
                    f"Point{point_index}={self._number(x)} {self._number(y)}"
                )
                lines.append(f"R_Wall{point_index}={self._number(self.room_settings['wall_reflectance'])}")
            lines.extend(["NrLums=0", "NrStruct=0", "NrFurns=0"])

        storeys = sorted({room["source_storey"] for room in rooms})
        manual_actions = [
            "In DIALux evo, choose File > Import > STF and import this file. This file contains rooms from one source storey; it does not create the building's native storey hierarchy.",
        ]
        warnings = [
            "STF has no building-storey elevation field. The exporter refuses multiple source storeys rather than flattening or moving them into a misleading layout.",
            "STF cannot create native DIALux storeys or set their elevations. Reorganizing rooms into true DIALux levels still requires DIALux editing.",
            "The native IFC importer is the DIALux route for preserving a multi-storey building hierarchy; availability depends on the installed DIALux license.",
            "Overlapping room footprints on the same storey are rejected because DIALux may split intersecting STF rooms into separate buildings.",
            "IFC doors, windows, curtain-wall subdivisions and arbitrary wall finishes are not created as native DIALux openings by the STF room importer.",
            "The required workplane, maintenance factor and reflectances use the configurable values shown in the app; they are lighting-design assumptions, not values recovered from the IFC geometry.",
        ]
        metadata = {
            "format": "DIALux evo STF room import",
            "format_version": "1.0.5",
            "application_version": APP_VERSION,
            "ifc_file": self.inspector.file_path,
            "ifc_schema": self.inspector.schema,
            "project_name": self.inspector.project_name,
            "source_length_unit": self.inspector.length_unit,
            "source_to_meters": self.inspector.unit_scale_to_meters,
            "room_defaults": self.room_settings,
            "source_storeys": storeys,
            "rooms": rooms,
            "manual_actions": manual_actions,
            "limitations": warnings,
        }
        return lines, metadata

    def _validate_room_settings(self) -> None:
        workplane = self.room_settings["workplane_m"]
        mf = self.room_settings["maintenance_factor"]
        if not math.isfinite(workplane) or not 0 < workplane < 1000:
            raise ValueError(
                "Room workplane must be a finite height greater than 0 and below 1000 metres. "
                "DIALux replaces a zero STF workplane with 0.85 m."
            )
        if not math.isfinite(mf) or not 0.01 < mf <= 1:
            raise ValueError("Maintenance factor must be greater than 0.01 and no greater than 1.")
        for key in ("ceiling_reflectance", "wall_reflectance", "floor_reflectance"):
            value = self.room_settings[key]
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be between 0 and 1.")

    @staticmethod
    def _safe_stf_label(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value))
        text = text.encode("latin-1", errors="ignore").decode("latin-1")
        text = "".join("-" if char in "=[]" else " " if ord(char) < 32 or 127 <= ord(char) < 160 else char for char in text)
        text = " ".join(text.split()).strip(" .")
        if not text:
            text = "Room"
        return text[:MAX_STF_LABEL_LENGTH].rstrip(" .") or "Room"

    @staticmethod
    def _number(value: float) -> str:
        if not math.isfinite(value):
            raise ValueError("STF cannot contain a non-finite number.")
        if abs(value) < 5e-13:
            return "0"
        return format(value, ".12g")

    @staticmethod
    def _write_pair_atomically(stf_path: str, sidecar_path: str, stf_data: bytes, sidecar_data: bytes) -> None:
        staging: list[tuple[str, str]] = []
        try:
            for destination, content in ((stf_path, stf_data), (sidecar_path, sidecar_data)):
                temp_path = destination + ".tmp"
                with open(temp_path, "wb") as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
                staging.append((temp_path, destination))
            for source, destination in staging:
                os.replace(source, destination)
        finally:
            for source, _ in staging:
                if os.path.exists(source):
                    os.remove(source)

    @staticmethod
    def _report(callback: ProgressCallback | None, fraction: float, description: str) -> None:
        if callback is not None:
            callback(fraction, description)

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("DIALux room export was cancelled.")
