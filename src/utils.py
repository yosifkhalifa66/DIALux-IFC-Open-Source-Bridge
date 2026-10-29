"""Logging, configuration, material defaults, and application helpers."""
import json
import logging
import os
import platform
import sys
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict

from . import __version__

APP_VERSION = __version__

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logger() -> logging.Logger:
    log = logging.getLogger("DialuxIFC")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(ch)
        try:
            log_dir = os.path.join(tempfile.gettempdir(), "DialuxIFCBridge")
            os.makedirs(log_dir, exist_ok=True)
            fh = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            log.addHandler(fh)
        except OSError as exc:
            log.warning("File logging is unavailable: %s", exc)
    return log

logger = _setup_logger()

# ---------------------------------------------------------------------------
# Unit conversion table  (source unit name → multiplier to SI Meters)
# ---------------------------------------------------------------------------
UNIT_TO_METERS: Dict[str, float] = {
    # SI
    "METRE": 1.0,      "METER": 1.0,      "METRES": 1.0,     "METERS": 1.0,     "M": 1.0,
    "MILLIMETRE": 0.001, "MILLIMETER": 0.001, "MILLIMETRES": 0.001, "MILLIMETERS": 0.001, "MM": 0.001,
    "CENTIMETRE": 0.01,  "CENTIMETER": 0.01,  "CENTIMETRES": 0.01,  "CENTIMETERS": 0.01,  "CM": 0.01,
    "DECIMETRE": 0.1,    "DECIMETER": 0.1,
    # Imperial
    "FOOT": 0.3048,     "FEET": 0.3048,     "FT": 0.3048,
    "INCH": 0.0254,     "INCHES": 0.0254,   "IN": 0.0254,
    "YARD": 0.9144,     "YARDS": 0.9144,    "YD": 0.9144,
}

# ---------------------------------------------------------------------------
# Default visualization material library.
# These fallback colors are not verified lighting reflectances.
#   name  – OBJ material name
#   Kd    – diffuse RGB  (0-1)
#   Ks    – specular RGB
#   d     – dissolve / opacity  (1.0 = opaque, <1 = semi-transparent)
#   desc  – human label
# ---------------------------------------------------------------------------
DEFAULT_MATERIALS: Dict[str, Dict[str, Any]] = {
    # Walls
    "IfcWall":              {"name": "Wall_75",          "Kd": (0.75, 0.75, 0.75), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Interior/Exterior Wall (75 % reflectance)"},
    "IfcWallStandardCase":  {"name": "Wall_75",          "Kd": (0.75, 0.75, 0.75), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Standard Wall (75 % reflectance)"},
    # Glazing
    "IfcCurtainWall":       {"name": "CurtainWall_Glass", "Kd": (0.15, 0.30, 0.40), "Ks": (0.70, 0.70, 0.80), "d": 0.30, "desc": "Fallback curtain-wall appearance; transmittance unknown"},
    "IfcWindow":            {"name": "Window_Glass",      "Kd": (0.15, 0.30, 0.40), "Ks": (0.80, 0.80, 0.90), "d": 0.25, "desc": "Fallback window appearance; transmittance unknown"},
    # Horizontal
    "IfcSlab":              {"name": "Slab_35",           "Kd": (0.35, 0.35, 0.35), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Floor / Ceiling Slab (35 % reflectance)"},
    "IfcRoof":              {"name": "Roof_30",           "Kd": (0.40, 0.35, 0.30), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Roof Construction"},
    "IfcPlate":             {"name": "Plate_Metal",       "Kd": (0.55, 0.55, 0.58), "Ks": (0.40, 0.40, 0.40), "d": 1.0, "desc": "Metal Plate / Cladding Panel"},
    # Openings
    "IfcDoor":              {"name": "Door_Wood",         "Kd": (0.45, 0.30, 0.18), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Door Leaf & Frame"},
    "IfcOpeningElement":    {"name": "Opening_Void",      "Kd": (0.10, 0.10, 0.10), "Ks": (0.00, 0.00, 0.00), "d": 0.15, "desc": "Opening / Void"},
    # Structural
    "IfcColumn":            {"name": "Column_Struct",     "Kd": (0.60, 0.60, 0.60), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Structural Column"},
    "IfcBeam":              {"name": "Beam_Struct",       "Kd": (0.55, 0.55, 0.55), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Structural Beam"},
    "IfcMember":            {"name": "Member_Struct",     "Kd": (0.55, 0.55, 0.55), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Structural Member"},
    "IfcFooting":           {"name": "Footing_Concrete",  "Kd": (0.40, 0.40, 0.40), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Foundation / Footing"},
    "IfcPile":              {"name": "Pile_Concrete",     "Kd": (0.40, 0.40, 0.40), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Foundation Pile"},
    # Circulation
    "IfcStair":             {"name": "Stair_Concrete",    "Kd": (0.45, 0.45, 0.45), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Stairs & Landings"},
    "IfcStairFlight":       {"name": "Stair_Concrete",    "Kd": (0.45, 0.45, 0.45), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Stair Flight"},
    "IfcRamp":              {"name": "Ramp_Concrete",     "Kd": (0.45, 0.45, 0.45), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Ramp"},
    "IfcRampFlight":        {"name": "Ramp_Concrete",     "Kd": (0.45, 0.45, 0.45), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Ramp Flight"},
    "IfcRailing":           {"name": "Railing_Metal",     "Kd": (0.30, 0.30, 0.35), "Ks": (0.40, 0.40, 0.40), "d": 1.0, "desc": "Guardrail / Handrail"},
    # Spaces & Zones
    "IfcSpace":             {"name": "Room_Boundary",     "Kd": (0.40, 0.60, 0.80), "Ks": (0.10, 0.10, 0.10), "d": 0.25, "desc": "Room / Space Boundary (DIALux Room Definition)"},
    "IfcZone":              {"name": "Zone_Boundary",     "Kd": (0.40, 0.70, 0.90), "Ks": (0.10, 0.10, 0.10), "d": 0.25, "desc": "Zone Boundary"},
    # Finishes & Furnishing
    "IfcCovering":          {"name": "Covering_Finish",   "Kd": (0.70, 0.70, 0.70), "Ks": (0.05, 0.05, 0.05), "d": 1.0, "desc": "Wall / Floor / Ceiling Finish"},
    "IfcFurnishingElement": {"name": "Furniture",         "Kd": (0.50, 0.45, 0.40), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Furniture & Fittings"},
    "IfcLightFixture":      {"name": "LightFixture",      "Kd": (0.95, 0.95, 0.70), "Ks": (0.90, 0.90, 0.90), "d": 1.0, "desc": "Luminaire / Light Fixture"},
    # Proxy / catch-all
    "IfcBuildingElementProxy": {"name": "Proxy_Generic",  "Kd": (0.60, 0.60, 0.60), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Generic Proxy Element"},
    # Default fallback
    "Default":              {"name": "Element_Default",   "Kd": (0.65, 0.65, 0.65), "Ks": (0.10, 0.10, 0.10), "d": 1.0, "desc": "Generic Building Element"},
}

# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------
def get_app_dir() -> str:
    """Return the application root directory."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_default_export_dir() -> str:
    """Return ~/Documents/DialuxIFCBridge/exports (user-writable)."""
    docs = os.path.join(os.path.expanduser("~"), "Documents", "DialuxIFCBridge", "exports")
    os.makedirs(docs, exist_ok=True)
    return docs

def sanitize_filename(name: str) -> str:
    """Strip filesystem-unsafe characters."""
    if not name:
        return "Unnamed"
    keep = (' ', '.', '_', '-')
    out = "".join(c for c in str(name) if c.isalnum() or c in keep).strip()
    return out or "Unnamed"

# ---------------------------------------------------------------------------
# User configuration persistence
# ---------------------------------------------------------------------------
def _config_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    base = os.path.join(base, "DialuxIFCBridge")
    return os.path.join(base, "config.json")

def load_config() -> dict:
    try:
        path = _config_path()
        with open(path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load configuration from %s: %s", path, exc)
        return {}
    if not isinstance(config, dict):
        logger.warning("Ignoring invalid application configuration at %s", path)
        return {}
    return config

def save_config(cfg: dict) -> None:
    if not isinstance(cfg, dict):
        raise TypeError("Application configuration must be a dictionary.")
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as config_file:
            json.dump(cfg, config_file, indent=2, ensure_ascii=False)
            config_file.write("\n")
        os.replace(temp_path, path)
    except OSError:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            logger.exception("Could not remove incomplete config file %s", temp_path)
        raise

# ---------------------------------------------------------------------------
# Debug bundle
# ---------------------------------------------------------------------------
def get_log_path() -> str:
    return os.path.join(tempfile.gettempdir(), "DialuxIFCBridge", "app.log")

def export_debug_info(ifc_path: str = None) -> str:
    """Create a zip with log + system info for bug reports."""
    try:
        out_dir = os.path.join(tempfile.gettempdir(), "DialuxIFCBridge")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zp = os.path.join(out_dir, f"debug_{ts}.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            lp = get_log_path()
            if os.path.exists(lp):
                zf.write(lp, "app.log")
            sysinfo = (
                f"Platform : {platform.platform()}\n"
                f"Python   : {sys.version}\n"
                f"App      : DIALux IFC Bridge v{APP_VERSION}\n"
            )
            if ifc_path and os.path.exists(ifc_path):
                sysinfo += f"IFC Path : {ifc_path}\nIFC Size : {os.path.getsize(ifc_path)} bytes\n"
            zf.writestr("system_info.txt", sysinfo)
        return zp
    except Exception as exc:
        logger.exception("Debug export failed")
        raise OSError("Could not create the troubleshooting archive.") from exc
