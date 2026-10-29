"""IFC inspection and spatial/semantic indexing for DIALux IFC Bridge."""

from __future__ import annotations

import math
import os
import threading
from typing import Any, Callable

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.unit

from .utils import logger

RELEVANT_CLASSES = (
    "IfcWall",
    "IfcCurtainWall",
    "IfcSlab",
    "IfcRoof",
    "IfcPlate",
    "IfcMember",
    "IfcDoor",
    "IfcWindow",
    "IfcColumn",
    "IfcBeam",
    "IfcFooting",
    "IfcPile",
    "IfcStair",
    "IfcStairFlight",
    "IfcRamp",
    "IfcRampFlight",
    "IfcRailing",
    "IfcCovering",
    "IfcBuildingElementProxy",
    "IfcFurnishingElement",
    "IfcLightFixture",
    "IfcSpace",
    "IfcZone",
)

ProgressCallback = Callable[[float, str], None]


class IfcModelInspector:
    """Loads an IFC once and indexes geometry-bearing products and rooms."""

    def __init__(self, file_path: str) -> None:
        self.file_path = os.path.abspath(file_path)
        self.ifc_file: Any = None
        self.project_name = "Unknown project"
        self.authoring_app = "Unknown"
        self.schema = "Unknown"
        self.length_unit = "Unknown"
        self.unit_scale_to_meters = 1.0
        self.storeys: list[dict[str, Any]] = []
        self.elements_by_class: dict[str, list[Any]] = {}
        self.element_to_storey: dict[str, str] = {}
        self.rooms: list[dict[str, Any]] = []
        self.space_boundaries: list[dict[str, Any]] = []
        self.total_elements_count = 0

    def load(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> "IfcModelInspector":
        if not os.path.isfile(self.file_path):
            raise FileNotFoundError(f"IFC file not found: {self.file_path}")
        if os.path.getsize(self.file_path) == 0:
            raise ValueError("The selected IFC file is empty.")

        file_size_mb = os.path.getsize(self.file_path) / (1024 * 1024)
        self._check_cancelled(cancel_event)
        self._report(progress_callback, 0.02, f"Opening IFC model ({file_size_mb:.1f} MB)...")
        logger.info("Opening IFC file %s (%d bytes)", self.file_path, os.path.getsize(self.file_path))
        self.ifc_file = ifcopenshell.open(self.file_path)
        self.schema = str(getattr(self.ifc_file, "schema", "IFC"))

        self._report(progress_callback, 0.12, "Reading project header and units...")
        self._extract_header()
        self._detect_units()
        self._report(progress_callback, 0.24, "Reading building storeys and rooms...")
        self._index_spatial_structure(progress_callback, cancel_event)
        self._report(progress_callback, 0.38, "Indexing building elements...")
        self._index_elements(progress_callback, cancel_event)
        self._report(progress_callback, 1.0, "IFC analysis complete.")
        logger.info(
            "Indexed %d products across %d categories, %d rooms and %d storeys",
            self.total_elements_count,
            len(self.elements_by_class),
            len(self.rooms),
            len(self.storeys),
        )
        return self

    @staticmethod
    def _report(callback: ProgressCallback | None, fraction: float, text: str) -> None:
        if callback is not None:
            callback(fraction, text)

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("IFC processing was cancelled.")

    def _extract_header(self) -> None:
        projects = self.ifc_file.by_type("IfcProject")
        if projects:
            self.project_name = str(getattr(projects[0], "Name", None) or "Unnamed project")
        header = getattr(self.ifc_file, "header", None)
        file_name = getattr(header, "file_name", None)
        authoring = getattr(file_name, "originating_system", None)
        if authoring:
            self.authoring_app = str(authoring)

    def _detect_units(self) -> None:
        unit_assignments = self.ifc_file.by_type("IfcUnitAssignment")
        length_unit = None
        for assignment in unit_assignments:
            for unit in getattr(assignment, "Units", ()) or ():
                if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                    length_unit = unit
                    break
            if length_unit is not None:
                break

        scale = float(ifcopenshell.util.unit.calculate_unit_scale(self.ifc_file))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"IFC contains an invalid length-unit scale: {scale!r}")
        self.unit_scale_to_meters = scale
        if length_unit is None:
            self.length_unit = "Unknown (assuming metres)"
            logger.warning("IFC has no length unit; geometry will be treated as metres")
        elif length_unit.is_a("IfcSIUnit"):
            prefix = getattr(length_unit, "Prefix", None)
            name = getattr(length_unit, "Name", "METRE")
            self.length_unit = f"{prefix or ''}{name}".upper()
        else:
            self.length_unit = str(getattr(length_unit, "Name", None) or length_unit.is_a())

    def _index_spatial_structure(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        model = self.ifc_file
        storey_entities = model.by_type("IfcBuildingStorey")
        self.storeys = []
        storey_names: dict[str, str] = {}
        entity_to_parent: dict[int, Any] = {}

        for relation in model.by_type("IfcRelAggregates"):
            parent = getattr(relation, "RelatingObject", None)
            for child in getattr(relation, "RelatedObjects", ()) or ():
                if parent is not None:
                    entity_to_parent[child.id()] = parent

        for storey in storey_entities:
            guid = str(getattr(storey, "GlobalId", "") or storey.id())
            name = str(getattr(storey, "Name", None) or "Unnamed storey")
            elevation = getattr(storey, "Elevation", None)
            elevation_raw = float(elevation) if elevation is not None else None
            elevation_m = (elevation_raw or 0.0) * self.unit_scale_to_meters
            storey_names[guid] = name
            self.storeys.append(
                {
                    "id": guid,
                    "name": name,
                    "elevation": elevation_m,
                    "elevation_raw": elevation_raw,
                    "elevation_defined": elevation_raw is not None,
                }
            )
        self.storeys.sort(key=lambda entry: (entry["elevation"], entry["name"].casefold()))

        spatial_storey: dict[int, str] = {storey.id(): storey_names[str(getattr(storey, "GlobalId", "") or storey.id())] for storey in storey_entities}
        product_to_spatial: dict[int, Any] = {}
        for relation in model.by_type("IfcRelContainedInSpatialStructure"):
            structure = getattr(relation, "RelatingStructure", None)
            if structure is None:
                continue
            for product in getattr(relation, "RelatedElements", ()) or ():
                product_to_spatial[product.id()] = structure

        storey_cache: dict[int, str | None] = {}

        def find_storey(spatial: Any) -> str | None:
            spatial_id = getattr(spatial, "id", None)
            if spatial_id is not None:
                sid = spatial_id()
                if sid in storey_cache:
                    return storey_cache[sid]
            seen: set[int] = set()
            current = spatial
            found_name: str | None = None
            path_ids: list[int] = []
            while current is not None and current.id() not in seen:
                cid = current.id()
                seen.add(cid)
                path_ids.append(cid)
                direct = spatial_storey.get(cid)
                if direct:
                    found_name = direct
                    break
                current = entity_to_parent.get(cid) or product_to_spatial.get(cid)
            for pid in path_ids:
                storey_cache[pid] = found_name
            return found_name

        self.element_to_storey.clear()
        products = model.by_type("IfcProduct")
        total_p = len(products)
        for idx, product in enumerate(products):
            if idx % 500 == 0:
                self._check_cancelled(cancel_event)
                if total_p > 0 and progress_callback is not None:
                    self._report(
                        progress_callback,
                        0.24 + 0.14 * (idx / total_p),
                        f"Resolving spatial hierarchy ({idx:,}/{total_p:,})...",
                    )
            spatial = product_to_spatial.get(product.id()) or product
            storey_name = find_storey(spatial)
            if storey_name:
                guid = getattr(product, "GlobalId", None) or f"step-{product.id()}"
                if guid:
                    self.element_to_storey[str(guid)] = storey_name

        if not self.storeys:
            self.storeys = [
                {
                    "id": "DEFAULT",
                    "name": "All Levels",
                    "elevation": 0.0,
                    "elevation_raw": None,
                    "elevation_defined": False,
                }
            ]

        self.rooms = []
        for space in model.by_type("IfcSpace"):
            guid = str(getattr(space, "GlobalId", "") or f"step-{space.id()}")
            self.rooms.append(
                {
                    "id": guid,
                    "name": str(getattr(space, "Name", None) or "Unnamed room"),
                    "long_name": getattr(space, "LongName", None),
                    "storey": self.element_to_storey.get(guid, "Unassigned"),
                    "composition_type": getattr(space, "CompositionType", None),
                    "interior_or_exterior": getattr(space, "InteriorOrExteriorSpace", None),
                }
            )

        self.space_boundaries = []
        for boundary in model.by_type("IfcRelSpaceBoundary"):
            space = getattr(boundary, "RelatingSpace", None)
            element = getattr(boundary, "RelatedBuildingElement", None)
            self.space_boundaries.append(
                {
                    "id": str(getattr(boundary, "GlobalId", "") or boundary.id()),
                    "space_id": (
                        str(getattr(space, "GlobalId", "") or f"step-{space.id()}") if space else None
                    ),
                    "element_id": (
                        str(getattr(element, "GlobalId", "") or f"step-{element.id()}") if element else None
                    ),
                    "physical_or_virtual": getattr(boundary, "PhysicalOrVirtualBoundary", None),
                    "internal_or_external": getattr(boundary, "InternalOrExternalBoundary", None),
                    "corresponding_boundary_id": (
                        str(getattr(getattr(boundary, "CorrespondingBoundary", None), "GlobalId", "") or "")
                        or None
                    ),
                }
            )

    def _index_elements(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        accepted_classes = set(RELEVANT_CLASSES)
        grouped: dict[str, list[Any]] = {}
        seen_guids: set[str] = set()
        class_accepted_cache: dict[str, bool] = {}
        products = self.ifc_file.by_type("IfcProduct")
        total = len(products)
        for index, product in enumerate(products):
            self._check_cancelled(cancel_event)
            try:
                ifc_class = str(product.is_a())
                accepted = class_accepted_cache.get(ifc_class)
                if accepted is None:
                    accepted = any(product.is_a(class_name) for class_name in accepted_classes)
                    class_accepted_cache[ifc_class] = accepted
                if not accepted:
                    continue
                guid = str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
                if guid in seen_guids:
                    continue
                seen_guids.add(guid)
                grouped.setdefault(ifc_class, []).append(product)
            except (RuntimeError, AttributeError, TypeError) as exc:
                logger.debug("Skipping unreadable IFC product at index %d: %s", index, exc)
            if total and index % 200 == 0:
                self._report(
                    progress_callback,
                    0.38 + 0.60 * (index + 1) / total,
                    f"Indexing element {index + 1:,} of {total:,} ({ifc_class})...",
                )

        for zone in self.ifc_file.by_type("IfcZone"):
            guid = str(getattr(zone, "GlobalId", "") or f"step-{zone.id()}")
            if guid not in seen_guids:
                grouped.setdefault("IfcZone", []).append(zone)
                seen_guids.add(guid)

        self.elements_by_class = dict(sorted(grouped.items()))
        self.total_elements_count = sum(len(items) for items in self.elements_by_class.values())
        fallback_storey = "All Levels" if len(self.storeys) == 1 and self.storeys[0]["name"] == "All Levels" else "Unassigned"
        unassigned_found = False
        for products_in_category in self.elements_by_class.values():
            for product in products_in_category:
                key = str(getattr(product, "GlobalId", "") or f"step-{product.id()}")
                if key not in self.element_to_storey:
                    self.element_to_storey[key] = fallback_storey
                    unassigned_found = fallback_storey == "Unassigned" or unassigned_found
        if unassigned_found and not any(storey["name"] == "Unassigned" for storey in self.storeys):
            self.storeys.append(
                {
                    "id": "UNASSIGNED",
                    "name": "Unassigned",
                    "elevation": 0.0,
                    "elevation_raw": None,
                    "elevation_defined": False,
                }
            )
        for room in self.rooms:
            room["storey"] = self.element_to_storey.get(room["id"], room["storey"])

    def get_summary(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "project_name": self.project_name,
            "authoring_app": self.authoring_app,
            "schema": self.schema,
            "detected_unit": self.length_unit,
            "unit_scale_to_meters": self.unit_scale_to_meters,
            "storeys": self.storeys,
            "total_elements": self.total_elements_count,
            "category_counts": {name: len(items) for name, items in self.elements_by_class.items()},
            "rooms": self.rooms,
            "space_boundaries_count": len(self.space_boundaries),
        }

    def get_tessellation_settings(self) -> ifcopenshell.geom.settings:
        settings = ifcopenshell.geom.settings()
        options = (
            ("USE_WORLD_COORDS", True),
            ("WELD_VERTICES", True),
            ("DISABLE_OPENING_SUBTRACTIONS", False),
            ("CONVERT_BACK_UNITS", True),
            ("APPLY_DEFAULT_MATERIALS", True),
        )
        for setting_name, value in options:
            setting = getattr(settings, setting_name, None)
            if setting is not None:
                settings.set(setting, value)
        return settings
