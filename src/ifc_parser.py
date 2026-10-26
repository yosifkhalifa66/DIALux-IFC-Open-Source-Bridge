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
            
        file_size = os.path.getsize(self.file_path)
        logger.info(f"Opening IFC file: {self.file_path} ({file_size} bytes)")
        try:
            self.ifc_file = ifcopenshell.open(self.file_path)
            self.schema = getattr(self.ifc_file, 'schema', 'IFC')
            logger.info(f"Opened IFC successfully, schema={self.schema}")
        except Exception as e:
            logger.error(f"Failed to open IFC with ifcopenshell: {e}", exc_info=True)
            raise
        
        try:
            logger.info("Extracting header info...")
            self._extract_header_info()
            logger.info("Header info extracted")
        except Exception as e:
            logger.warning(f"Header extraction failed: {e}")
        try:
            logger.info("Detecting units...")
            self._detect_units()
            logger.info(f"Units detected: {self.length_unit}")
        except Exception as e:
            logger.warning(f"Unit detection failed: {e}")
        try:
            logger.info("Extracting storeys...")
            self._extract_storeys()
            logger.info(f"Storeys extracted: {len(self.storeys)}")
        except Exception as e:
            logger.warning(f"Storey extraction failed: {e}")
        try:
            logger.info("Indexing elements...")
            self._index_elements()
            logger.info(f"Elements indexed: {self.total_elements_count}")
        except Exception as e:
            logger.warning(f"Element indexing failed: {e}")
        return True

    def _extract_header_info(self):
        """Extract project name and authoring software."""
        try:
            projects = self.ifc_file.by_type("IfcProject")
            if projects:
                p = projects[0]
                self.project_name = getattr(p, 'Name', None) or "Unnamed Project"
        except Exception as e:
            logger.warning(f"Could not extract project name: {e}")
            
        # Detect authoring application from header
        try:
            header = getattr(self.ifc_file, "header", None)
            if header is not None:
                if hasattr(header, "file_description") and header.file_description:
                    desc = getattr(header.file_description, "description", None)
                    if desc:
                        self.authoring_app = ", ".join(desc) if isinstance(desc, (list, tuple)) else str(desc)
                if hasattr(header, "file_name") and header.file_name:
                    app = getattr(header.file_name, "originating_system", None)
                    if app:
                        self.authoring_app = str(app)
        except Exception:
            pass

    def _detect_units(self):
        """Detect length unit and calculate scaling factor to Meters."""
        try:
            units = self.ifc_file.by_type("IfcUnitAssignment")
            if units:
                unit_assignment = units[0]
                unit_list = getattr(unit_assignment, 'Units', None)
                if unit_list:
                    for unit in unit_list:
                        try:
                            if unit.is_a("IfcSIUnit") and getattr(unit, 'UnitType', None) == "LENGTHUNIT":
                                prefix = getattr(unit, 'Prefix', None) or ""
                                name = getattr(unit, 'Name', '') or ''
                                unit_name = (prefix + name).upper()
                                self.length_unit = unit_name or "METERS"
                                self.unit_scale_to_meters = UNIT_TO_METERS.get(unit_name, 1.0)
                                logger.info(f"Detected length unit: {unit_name} (Scale to meters: {self.unit_scale_to_meters})")
                                return
                            elif unit.is_a("IfcConversionBasedUnit") and getattr(unit, 'UnitType', None) == "LENGTHUNIT":
                                name = getattr(unit, 'Name', '') or ""
                                unit_name = str(name).upper()
                                self.length_unit = unit_name or "METERS"
                                self.unit_scale_to_meters = UNIT_TO_METERS.get(unit_name, 1.0)
                                logger.info(f"Detected conversion unit: {unit_name} (Scale: {self.unit_scale_to_meters})")
                                return
                        except Exception:
                            continue
        except Exception as e:
            logger.warning(f"Error reading units, defaulting to METERS: {e}")
            
        self.length_unit = "METERS"
        self.unit_scale_to_meters = 1.0

    def _extract_storeys(self):
        """Extract all building storeys and map their contained elements."""
        try:
            storeys = self.ifc_file.by_type("IfcBuildingStorey")
        except Exception as e:
            logger.warning(f"Could not get storeys: {e}")
            storeys = []
        self.storeys = []
        
        for s in storeys:
            try:
                elevation = getattr(s, 'Elevation', None)
                elevation = float(elevation) if elevation is not None else 0.0
                storey_info = {
                    "id": getattr(s, 'GlobalId', ''),
                    "name": getattr(s, 'Name', None) or "Storey",
                    "elevation": elevation * self.unit_scale_to_meters,
                    "elevation_raw": elevation,
                }
                self.storeys.append(storey_info)
            except Exception as e:
                logger.debug(f"Error processing storey: {e}")
                continue
            
        # Sort storeys by elevation ascending
        self.storeys.sort(key=lambda x: x["elevation"])
        
        # Map elements to their parent storeys via spatial relations
        try:
            spatial_rels = self.ifc_file.by_type("IfcRelContainedInSpatialStructure")
            for rel in spatial_rels:
                try:
                    structure = getattr(rel, 'RelatingStructure', None)
                    structure_name = getattr(structure, 'Name', None) if structure else "Default Storey"
                    related = getattr(rel, 'RelatedElements', None) or []
                    for product in related:
                        try:
                            gid = getattr(product, 'GlobalId', None)
                            if gid:
                                self.element_to_storey[gid] = structure_name or "Default Storey"
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not map elements to storeys: {e}")

    def _index_elements(self):
        """Count and group all physical elements."""
        self.elements_by_class = {}
        self.total_elements_count = 0
        
        for cls_name in RELEVANT_CLASSES:
            try:
                elements = self.ifc_file.by_type(cls_name)
            except Exception:
                continue
            # Filter elements that have a representation
            valid_elements = []
            for e in elements:
                try:
                    if getattr(e, 'Representation', None) is not None:
                        valid_elements.append(e)
                except Exception:
                    continue
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
