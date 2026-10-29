"""Export an IFC wall/opening relationship and geometry inventory."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

import ifcopenshell.geom

from .coordinate_transform import CoordinateTransform
from .ifc_parser import IfcModelInspector
from .utils import logger

ProgressCallback = Callable[[float, str], None]

INVENTORY_CLASSES = (
    "IfcWall",
    "IfcSlab",
    "IfcCovering",
    "IfcDoor",
    "IfcWindow",
    "IfcOpeningElement",
    "IfcCurtainWall",
    "IfcColumn",
    "IfcBeam",
    "IfcMember",
    "IfcPlate",
    "IfcBuildingElementProxy",
    "IfcFurnishingElement",
    "IfcStair",
    "IfcStairFlight",
    "IfcRamp",
    "IfcRampFlight",
    "IfcRailing",
    "IfcRoof",
)

GEOMETRY_CLASSES = frozenset(INVENTORY_CLASSES) | {"IfcWallStandardCase"}


class IfcArchitectureInventoryExporter:
    """Writes source-linked wall/opening relations and transformed bounds."""

    def __init__(self, inspector: IfcModelInspector) -> None:
        self.inspector = inspector

    def export(
        self,
        output_json_path: str,
        *,
        coordinate_transform: CoordinateTransform,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        model = self.inspector.ifc_file
        if model is None:
            raise RuntimeError("Load an IFC model before creating its architecture inventory.")
        if os.path.splitext(output_json_path)[1].casefold() != ".json":
            raise ValueError("The architecture inventory output must use the .json extension.")
        output_path = Path(output_json_path).resolve()
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite an existing architecture inventory: {output_path}")
        if not math.isclose(
            coordinate_transform.source_unit_to_meters,
            self.inspector.unit_scale_to_meters,
            rel_tol=1e-12,
        ):
            raise ValueError("The inventory transform source units do not match the IFC length units.")

        products_by_id: dict[int, Any] = {}
        for ifc_class in INVENTORY_CLASSES:
            for product in model.by_type(ifc_class):
                products_by_id[product.id()] = product
        products = sorted(products_by_id.values(), key=lambda product: product.id())

        opening_hosts: dict[int, list[Any]] = {}
        for relation in model.by_type("IfcRelVoidsElement"):
            opening = getattr(relation, "RelatedOpeningElement", None)
            host = getattr(relation, "RelatingBuildingElement", None)
            if opening is not None and host is not None:
                opening_hosts.setdefault(opening.id(), []).append(host)

        opening_fillings: dict[int, list[Any]] = {}
        for relation in model.by_type("IfcRelFillsElement"):
            opening = getattr(relation, "RelatingOpeningElement", None)
            filling = getattr(relation, "RelatedBuildingElement", None)
            if opening is not None and filling is not None:
                opening_fillings.setdefault(opening.id(), []).append(filling)

        aggregate_children: dict[int, list[Any]] = {}
        aggregate_parents: dict[int, list[Any]] = {}
        assemblies = []
        for relation in [*model.by_type("IfcRelAggregates"), *model.by_type("IfcRelNests")]:
            parent = getattr(relation, "RelatingObject", None)
            children = list(getattr(relation, "RelatedObjects", ()) or ())
            if parent is None:
                continue
            aggregate_children.setdefault(parent.id(), []).extend(children)
            for child in children:
                aggregate_parents.setdefault(child.id(), []).append(parent)
            assemblies.append(
                {
                    "relationship_type": str(relation.is_a()),
                    "parent": self._identity(parent),
                    "components": [
                        self._identity(child)
                        for child in sorted(children, key=lambda item: item.id())
                    ],
                }
            )

        opening_entities = {
            opening.id(): opening for opening in model.by_type("IfcOpeningElement")
        }
        relationships = self._relationship_records(
            opening_entities,
            opening_hosts,
            opening_fillings,
        )
        settings = self.inspector.get_tessellation_settings()
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        geometry_products = [
            product for product in products if product.is_a() in GEOMETRY_CLASSES
        ]
        geometry_product_ids = {product.id() for product in geometry_products}
        total = len(products)
        for index, product in enumerate(products):
            self._check_cancelled(cancel_event)
            ifc_type = str(product.is_a())
            global_id = str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
            record: dict[str, Any] = {
                "global_id": global_id,
                "step_id": product.id(),
                "ifc_type": ifc_type,
                "name": getattr(product, "Name", None),
                "object_type": getattr(product, "ObjectType", None),
                "has_representation": getattr(product, "Representation", None) is not None,
                "storey": self.inspector.element_to_storey.get(global_id, "Unassigned"),
                "hosts": [
                    self._identity(host)
                    for host in sorted(opening_hosts.get(product.id(), []), key=lambda item: item.id())
                ],
                "fillings": [
                    self._identity(filling)
                    for filling in sorted(opening_fillings.get(product.id(), []), key=lambda item: item.id())
                ],
                "components": [
                    self._identity(component)
                    for component in sorted(
                        aggregate_children.get(product.id(), []),
                        key=lambda item: item.id(),
                    )
                ],
                "aggregate_parents": [
                    self._identity(parent)
                    for parent in sorted(
                        aggregate_parents.get(product.id(), []),
                        key=lambda item: item.id(),
                    )
                ],
            }
            if product.id() in geometry_product_ids:
                bounds, warning = self._geometry_bounds(
                    product,
                    settings,
                    coordinate_transform,
                )
                record["geometry_bounds"] = bounds
                if warning:
                    warning_text = f"{ifc_type} {global_id}: {warning}"
                    warnings.append(warning_text)
                    record["geometry_warning"] = warning
                    logger.warning("Architecture inventory geometry skipped: %s", warning_text)
            records.append(record)
            if total and (index % 25 == 0 or index + 1 == total):
                self._report(
                    progress_callback,
                    (index + 1) / total,
                    f"Inventorying architectural element {index + 1:,} of {total:,}...",
                )

        summary = self._summary(products, relationships, assemblies, warnings)
        document = {
            "format": "DIALux IFC Bridge architecture inventory",
            "format_version": 1,
            "source_file": self.inspector.file_path,
            "source_schema": self.inspector.schema,
            "source_length_unit": self.inspector.length_unit,
            "source_unit_to_meters": self.inspector.unit_scale_to_meters,
            "coordinate_transform": coordinate_transform.to_metadata(),
            "geometry_bounds_frame": "shared local project coordinates, metres",
            "summary": summary,
            "relationships": relationships,
            "assemblies": assemblies,
            "elements": records,
            "warnings": warnings,
        }
        self._write_atomically(output_path, document)
        self._report(progress_callback, 1.0, "IFC architecture inventory created.")
        return {
            "inventory_path": str(output_path),
            "element_count": len(records),
            "geometry_element_count": len(geometry_products),
            "warning_count": len(warnings),
            "summary": summary,
        }

    def _geometry_bounds(
        self,
        product: Any,
        settings: ifcopenshell.geom.settings,
        coordinate_transform: CoordinateTransform,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            shape = ifcopenshell.geom.create_shape(settings, product).geometry
            vertices = shape.verts
        except Exception as exc:
            return None, f"tessellation failed ({type(exc).__name__}: {exc})"
        if len(vertices) < 3 or len(vertices) % 3:
            return None, "tessellation returned no complete XYZ vertices"
        source_points = [
            tuple(float(vertices[offset + axis]) for axis in range(3))
            for offset in range(0, len(vertices), 3)
        ]
        if not all(math.isfinite(value) for point in source_points for value in point):
            return None, "tessellation returned non-finite vertex coordinates"
        world_points_m = [
            tuple(value * self.inspector.unit_scale_to_meters for value in point)
            for point in source_points
        ]
        local_points_m = [
            coordinate_transform.to_project_point_m(point)
            for point in world_points_m
        ]
        world_min, world_max = self._bounds(world_points_m)
        project_min, project_max = self._bounds(local_points_m)
        return (
            {
                "world_min_m": world_min,
                "world_max_m": world_max,
                "project_min_m": project_min,
                "project_max_m": project_max,
                "vertex_count": len(source_points),
            },
            None,
        )

    @staticmethod
    def _bounds(
        points: list[tuple[float, float, float]],
    ) -> tuple[list[float], list[float]]:
        return (
            [min(point[axis] for point in points) for axis in range(3)],
            [max(point[axis] for point in points) for axis in range(3)],
        )

    @classmethod
    def _relationship_records(
        cls,
        opening_entities: dict[int, Any],
        opening_hosts: dict[int, list[Any]],
        opening_fillings: dict[int, list[Any]],
    ) -> list[dict[str, Any]]:
        records = []
        opening_ids = set(opening_entities) | set(opening_hosts) | set(opening_fillings)
        for opening_id in sorted(opening_ids):
            opening = opening_entities.get(opening_id)
            opening_identity = (
                cls._identity(opening)
                if opening is not None
                else {"step_id": opening_id}
            )
            hosts = sorted(opening_hosts.get(opening_id, []), key=lambda item: item.id())
            fillings = sorted(opening_fillings.get(opening_id, []), key=lambda item: item.id())
            records.append(
                {
                    "opening": opening_identity,
                    "hosts": [cls._identity(host) for host in hosts],
                    "fillings": [cls._identity(filling) for filling in fillings],
                }
            )
        return records

    @staticmethod
    def _identity(product: Any) -> dict[str, Any]:
        return {
            "global_id": str(getattr(product, "GlobalId", "") or f"step-{product.id()}"),
            "step_id": product.id(),
            "ifc_type": str(product.is_a()),
            "name": getattr(product, "Name", None),
        }

    @staticmethod
    def _summary(
        products: list[Any],
        relationships: list[dict[str, Any]],
        assemblies: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for product in products:
            ifc_type = str(product.is_a())
            by_type[ifc_type] = by_type.get(ifc_type, 0) + 1
        host_types: dict[str, int] = {}
        filling_types: dict[str, int] = {}
        curtain_wall_assemblies = [
            assembly
            for assembly in assemblies
            if assembly["parent"]["ifc_type"] == "IfcCurtainWall"
        ]
        curtain_wall_component_types: dict[str, int] = {}
        for assembly in curtain_wall_assemblies:
            for component in assembly["components"]:
                component_type = component["ifc_type"]
                curtain_wall_component_types[component_type] = (
                    curtain_wall_component_types.get(component_type, 0) + 1
                )
        for opening in relationships:
            for host in opening["hosts"]:
                host_types[host["ifc_type"]] = host_types.get(host["ifc_type"], 0) + 1
            for filling in opening["fillings"]:
                filling_types[filling["ifc_type"]] = filling_types.get(filling["ifc_type"], 0) + 1
        return {
            "element_count": len(products),
            "counts_by_ifc_type": dict(sorted(by_type.items())),
            "assembly_relationship_count": len(assemblies),
            "curtain_wall_assembly_count": len(curtain_wall_assemblies),
            "curtain_wall_component_counts_by_ifc_type": dict(
                sorted(curtain_wall_component_types.items())
            ),
            "opening_count": len(relationships),
            "opening_count_with_hosts": sum(bool(item["hosts"]) for item in relationships),
            "opening_count_with_fillings": sum(bool(item["fillings"]) for item in relationships),
            "opening_count_without_host": sum(not item["hosts"] for item in relationships),
            "filling_count": sum(len(item["fillings"]) for item in relationships),
            "host_counts_by_ifc_type": dict(sorted(host_types.items())),
            "filling_counts_by_ifc_type": dict(sorted(filling_types.items())),
            "geometry_warning_count": len(warnings),
        }

    @staticmethod
    def _write_atomically(path: Path, document: dict[str, Any]) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = output.name
                json.dump(document, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite an existing architecture inventory: {path}")
            os.replace(temporary_path, path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("IFC architecture inventory was cancelled.")

    @staticmethod
    def _report(
        callback: ProgressCallback | None,
        fraction: float,
        description: str,
    ) -> None:
        if callback is not None:
            callback(fraction, description)
