"""
Utility functions, constants, and unit converters for DIALux IFC Bridge.
"""
import os
import sys
import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DialuxIFC")

# Standard unit multipliers to Meters (DIALux evo SI unit)
UNIT_TO_METERS = {
    "METERS": 1.0,
    "M": 1.0,
    "MILLIMETERS": 0.001,
    "MILLIMETRE": 0.001,
    "MM": 0.001,
    "CENTIMETERS": 0.01,
    "CENTIMETRE": 0.01,
    "CM": 0.01,
    "FEET": 0.3048,
    "FOOT": 0.3048,
    "FT": 0.3048,
    "INCHES": 0.0254,
    "INCH": 0.0254,
    "IN": 0.0254,
}

# Standard lighting reflectance defaults (Kd RGB values)
# In lighting design (CIE / EN 12464-1):
# Ceiling: ~0.70 - 0.90
# Walls: ~0.50 - 0.80
# Floor: ~0.10 - 0.30
DEFAULT_MATERIALS = {
    "IfcWall": {
        "name": "Wall_Reflectance_70",
        "Kd": (0.75, 0.75, 0.75),
        "Ks": (0.05, 0.05, 0.05),
        "d": 1.0,
        "desc": "Interior/Exterior Wall (75% reflectance)"
    },
    "IfcWallStandardCase": {
        "name": "Wall_Reflectance_70",
        "Kd": (0.75, 0.75, 0.75),
        "Ks": (0.05, 0.05, 0.05),
        "d": 1.0,
        "desc": "Standard Wall (75% reflectance)"
    },
    "IfcSlab": {
        "name": "Slab_Floor_Reflectance_25",
        "Kd": (0.35, 0.35, 0.35),
        "Ks": (0.05, 0.05, 0.05),
        "d": 1.0,
        "desc": "Floor / Ceiling Slab (35% reflectance)"
    },
    "IfcRoof": {
        "name": "Roof_Reflectance_30",
        "Kd": (0.40, 0.35, 0.30),
        "Ks": (0.05, 0.05, 0.05),
        "d": 1.0,
        "desc": "Roof Construction"
    },
    "IfcDoor": {
        "name": "Door_Wood_Reflectance_30",
        "Kd": (0.45, 0.30, 0.18),
        "Ks": (0.1, 0.1, 0.1),
        "d": 1.0,
        "desc": "Door Leaf & Frame"
    },
    "IfcWindow": {
        "name": "Window_Glass_Clear",
        "Kd": (0.15, 0.30, 0.40),
        "Ks": (0.8, 0.8, 0.9),
        "d": 0.25, # Transparent
        "desc": "Clear Glazing (transmittance ~80%)"
    },
    "IfcCurtainWall": {
        "name": "CurtainWall_Glass",
        "Kd": (0.15, 0.30, 0.40),
        "Ks": (0.7, 0.7, 0.8),
        "d": 0.30,
        "desc": "Facade Glazing"
    },
    "IfcColumn": {
        "name": "Column_Structural",
        "Kd": (0.60, 0.60, 0.60),
        "Ks": (0.1, 0.1, 0.1),
        "d": 1.0,
        "desc": "Structural Column"
    },
    "IfcBeam": {
        "name": "Beam_Structural",
        "Kd": (0.55, 0.55, 0.55),
        "Ks": (0.1, 0.1, 0.1),
        "d": 1.0,
        "desc": "Structural Beam"
    },
    "IfcStair": {
        "name": "Stair_Concrete",
        "Kd": (0.45, 0.45, 0.45),
        "Ks": (0.05, 0.05, 0.05),
        "d": 1.0,
        "desc": "Stairs & Landings"
    },
    "IfcRailing": {
        "name": "Railing_Metal",
        "Kd": (0.30, 0.30, 0.35),
        "Ks": (0.4, 0.4, 0.4),
        "d": 1.0,
        "desc": "Guardrail / Handrail"
    },
    "IfcSpace": {
        "name": "Space_Zone_Boundary",
        "Kd": (0.2, 0.6, 0.8),
        "Ks": (0.1, 0.1, 0.1),
        "d": 0.15,
        "desc": "Room / Space Volume"
    },
    "IfcFurnishingElement": {
        "name": "Furniture_Default",
        "Kd": (0.50, 0.45, 0.40),
        "Ks": (0.1, 0.1, 0.1),
        "d": 1.0,
        "desc": "Furniture & Interior Fittings"
    },
    "IfcLightFixture": {
        "name": "LightFixture_Marker",
        "Kd": (0.95, 0.95, 0.70),
        "Ks": (0.9, 0.9, 0.9),
        "d": 1.0,
        "desc": "Luminaire / Light Fixture Position"
    },
    "Default": {
        "name": "BuildingElement_Default",
        "Kd": (0.65, 0.65, 0.65),
        "Ks": (0.1, 0.1, 0.1),
        "d": 1.0,
        "desc": "Generic Building Element"
    }
}

def get_app_dir() -> str:
    """Return the base application directory."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_default_export_dir() -> str:
    """Return a clean default output folder for converted models."""
    base = os.path.join(get_app_dir(), "exports")
    os.makedirs(base, exist_ok=True)
    return base

def sanitize_filename(name: str) -> str:
    """Clean strings for filesystem usage."""
    keepcharacters = (' ', '.', '_', '-')
    return "".join(c for c in name if c.isalnum() or c in keepcharacters).rstrip()
