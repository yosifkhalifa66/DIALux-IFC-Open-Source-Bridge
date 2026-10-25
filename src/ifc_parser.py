"""
IFC Model Parser & Metadata Inspector using IfcOpenShell.
Extracts project hierarchy, storeys, element categories, and tessellated geometry.
"""
import os
import ifcopenshell
import ifcopenshell.geom
from typing import Dict, List, Any, Optional
from .utils import logger, UNIT_TO_METERS

# Supported IFC classes organized for lighting & architectural design
RELEVANT_CLASSES = [
    "IfcWall",
    "IfcWallStandardCase",
    "IfcSlab",
    "IfcRoof",
    "IfcDoor",
    "IfcWindow",
    "IfcCurtainWall",
    "IfcColumn",
    "IfcBeam",
    "IfcStair",
    "IfcRailing",
    "IfcSpace",
    "IfcFurnishingElement",
    "IfcLightFixture",
]

class IfcModelInspector:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.ifc_file: Optional[ifcopenshell.file] = None
        self.project_name = "Unknown Project"
        self.authoring_app = "Unknown BIM Tool"
        self.schema = "IFC"
        self.length_unit = "METERS"
        self.unit_scale_to_meters = 1.0
        self.storeys: List[Dict[str, Any]] = []
        self.elements_by_class: Dict[str, List[Any]] = {}
        self.element_to_storey: Dict[str, str] = {}
        self.total_elements_count = 0
        
    def load(self) -> bool:
        """Load and parse the IFC header and spatial structure."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"IFC file not found: {self.file_path}")
            
        logger.info(f"Opening IFC file: {self.file_path}")
        self.ifc_file = ifcopenshell.open(self.file_path)
        self.schema = self.ifc_file.schema
        
        self._extract_header_info()
        self._detect_units()
        self._extract_storeys()
        self._index_elements()
        return True

    def _extract_header_info(self):
        """Extract project name and authoring software."""
        projects = self.ifc_file.by_type("IfcProject")
        if projects:
            p = projects[0]
            self.project_name = p.Name or "Unnamed Project"
            
        # Detect authoring application from header
        try:
            header = self.ifc_file.header
            if hasattr(header, "file_description") and header.file_description:
                desc = header.file_description.description
                if desc:
                    self.authoring_app = ", ".join(desc)
            if hasattr(header, "file_name") and header.file_name:
                app = header.file_name.originating_system
                if app:
                    self.authoring_app = app
        except Exception:
            pass

    def _detect_units(self):
        """Detect length unit and calculate scaling factor to Meters."""
        try:
            units = self.ifc_file.by_type("IfcUnitAssignment")
            if units:
                for unit in units[0].Units:
                    if unit.is_a("IfcSIUnit") and unit.UnitType == "LENGTHUNIT":
                        prefix = unit.Prefix or ""
                        unit_name = (prefix + unit.Name).upper()
                        self.length_unit = unit_name
                        self.unit_scale_to_meters = UNIT_TO_METERS.get(unit_name, 1.0)
                        logger.info(f"Detected length unit: {unit_name} (Scale to meters: {self.unit_scale_to_meters})")
                        return
                    elif unit.is_a("IfcConversionBasedUnit") and unit.UnitType == "LENGTHUNIT":
                        unit_name = (unit.Name or "").upper()
                        self.length_unit = unit_name
                        self.unit_scale_to_meters = UNIT_TO_METERS.get(unit_name, 1.0)
                        logger.info(f"Detected conversion unit: {unit_name} (Scale: {self.unit_scale_to_meters})")
                        return
        except Exception as e:
            logger.warning(f"Error reading units, defaulting to METERS: {e}")
            
        self.length_unit = "METERS"
        self.unit_scale_to_meters = 1.0

    def _extract_storeys(self):
        """Extract all building storeys and map their contained elements."""
        storeys = self.ifc_file.by_type("IfcBuildingStorey")
        self.storeys = []
        
        for s in storeys:
            elevation = float(s.Elevation) if s.Elevation is not None else 0.0
            storey_info = {
                "id": s.GlobalId,
                "name": s.Name or "Storey",
                "elevation": elevation * self.unit_scale_to_meters,
                "elevation_raw": elevation,
            }
            self.storeys.append(storey_info)
            
        # Sort storeys by elevation ascending
        self.storeys.sort(key=lambda x: x["elevation"])
        
        # Map elements to their parent storeys via spatial relations
        spatial_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
        for rel in spatial_rels:
            structure = rel.RelatingStructure
            structure_name = structure.Name if structure else "Default Storey"
            for product in rel.RelatedElements:
                self.element_to_storey[product.GlobalId] = structure_name

    def _index_elements(self):
        """Count and group all physical elements."""
        self.elements_by_class = {}
        self.total_elements_count = 0
        
        for cls_name in RELEVANT_CLASSES:
            elements = self.ifc_file.by_type(cls_name)
            # Filter elements that have a representation
            valid_elements = [e for e in elements if e.Representation is not None]
            if valid_elements:
                self.elements_by_class[cls_name] = valid_elements
                self.total_elements_count += len(valid_elements)

    def get_summary(self) -> Dict[str, Any]:
        """Return a structured summary for the UI."""
        category_counts = {cls: len(elements) for cls, elements in self.elements_by_class.items()}
        return {
            "project_name": self.project_name,
            "authoring_app": self.authoring_app,
            "schema": self.schema,
            "detected_unit": self.length_unit,
            "unit_scale_to_meters": self.unit_scale_to_meters,
            "storeys": self.storeys,
            "total_elements": self.total_elements_count,
            "category_counts": category_counts,
        }

    def get_tessellation_settings(self, scale_override: Optional[float] = None) -> ifcopenshell.geom.settings:
        """Create optimized geometry tessellation settings."""
        s = ifcopenshell.geom.settings()
        s.set(s.USE_WORLD_COORDS, True)
        s.set(s.WELD_VERTICES, True)
        return s
