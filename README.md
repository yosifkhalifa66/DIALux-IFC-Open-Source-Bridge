# ⚡ DIALux IFC Bridge

> **Free, seamless IFC & Revit BIM import for DIALux evo without a paid subscription.**

[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows)](https://microsoft.com)
[![DIALux evo](https://img.shields.io/badge/DIALux_evo-Compatible-E30613?style=flat-square)](https://www.dialux.com)
[![IFC Support](https://img.shields.io/badge/IFC-IFC2X3%20%7C%20IFC4%20%7C%20IFC4X3-blue?style=flat-square)](https://www.buildingsmart.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## 💡 Overview

DIALux evo restricts direct **IFC BIM import** behind the paid *DIALux Pro* subscription. However, DIALux evo's free tier has native support for **Wavefront OBJ 3D objects** and **3D AutoCAD DXF CAD underlays**.

**DIALux IFC Bridge** bridges the gap. It is a standalone desktop application with a clean dark-mode UI that allows you to drag-and-drop any standard IFC file, automatically converts the building envelope, storeys, spaces, and architectural geometry into DIALux-optimized 3D models with proper real-world SI scale (Meters) and photometric reflectances, and features a **1-click "Send to DIALux"** button that transfers the model straight into DIALux evo.

---

## ✨ Features

- **🎯 Drag & Drop Simplicity**: Drop any `.ifc` file directly onto the application window or use the file browser.
- **🚀 One-Click "Send to DIALux"**:
  - Automatically exports the geometry.
  - Places the converted `.obj` / `.mtl` onto the Windows Clipboard in `CF_HDROP` format.
  - Automatically activates or launches DIALux evo so you can simply press <kbd>Ctrl</kbd> + <kbd>V</kbd> or drag the file into your 3D view.
- **📏 Automatic Unit Scaling**: Correctly detects source model length units (Millimeters, Meters, Feet, Inches) and normalizes coordinates to SI **Meters** so lighting calculations and dimensions are 100% accurate.
- **🏢 Building Hierarchy & Storey Splitting**:
  - Automatically detects building storeys (`IfcBuildingStorey`).
  - Option to filter specific storeys or export individual levels separately.
- **🧱 Category Filtering**:
  - Selectively export: Walls, Slabs, Ceilings, Windows, Doors, Curtain Walls, Columns, Beams, Roofs, Stairs, and Spaces.
- **💡 Photometric Material Reflectance**:
  - Generates companion `.mtl` material definitions with standard lighting design reflectances (CIE / EN 12464-1):
    - **Ceilings**: ~80% reflectance (clean diffuse white)
    - **Walls**: ~75% reflectance (light gray/white)
    - **Floors**: ~35% reflectance (medium gray)
    - **Glazing / Windows**: Semi-transparent (transmittance ~80%)
    - **Doors / Wood**: ~30% reflectance
- **📐 3D DXF CAD Underlay Export**: Optional generation of 3D DXF files with `3DFACE` entities for users who prefer snapping to CAD plans.
- **📦 Standalone Executable**: No Python or dependencies required for end users.

---

## 🖥️ User Interface Preview

```
+--------------------------------------------------------------------------------+
|  ⚡ DIALux IFC Bridge    Free IFC & Revit BIM Import for DIALux evo   [🟢 DIALux] |
+--------------------------------------------------------------------------------+
|  [==========================================================================]  |
|  |                 📁 Drag & Drop your .IFC file here                        |  |
|  |                        — or click to Browse —                            |  |
|  [==========================================================================]  |
+---------------------------------------------------+----------------------------+
|  BIM Model Inspection                             |  Export & Transfer Settings|
|                                                   |                            |
|  🏢 Sample Building (Revit 2027, IFC4)            |  Unit Scale:               |
|  Unit: Millimeters -> Auto-scaled to Meters       |  [ Automatic (from IFC) v] |
|                                                   |                            |
|  📍 Building Storeys                              |  Hierarchy Grouping:       |
|  [x] Ground Floor (Elev: 0.00m)                   |  [ By Storey & Category v] |
|  [x] Level 1 (Elev: 3.50m)                        |                            |
|                                                   |  ------------------------- |
|  🧱 Architectural Categories                      |  [ 🚀 Send to DIALux evo ] |
|  [x] Walls (128)                                  |  (Copies to CF_HDROP &     |
|  [x] Slabs & Ceilings (14)                        |   activates DIALux window) |
|  [x] Windows (42)                                 |                            |
|  [x] Doors (18)                                   |  [ 💾 Export OBJ As...   ] |
|  [x] Columns (24)                                 |  [ 📐 Export 3D DXF      ] |
|  [ ] Furniture (310)                              |  [ 📁 Open Output Folder ] |
+---------------------------------------------------+----------------------------+
|  [======                   ] 35% Tessellating: Wall North                      |
+--------------------------------------------------------------------------------+
```

---

## 🚀 Quick Start

### Option A: Run Precompiled Executable (.exe)
1. Download `DialuxIFCBridge.exe` from the [Releases](releases) tab.
2. Double-click `DialuxIFCBridge.exe` to launch.
3. Drop your `.ifc` file and click **Send to DIALux**.

### Option B: Run from Source
1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/dialux-ifc-drag-drop.git
   cd dialux-ifc-drag-drop
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

---

## 🛠️ Building the Standalone Executable (.exe)

To compile the application into a standalone Windows binary:
```bash
python build_exe.py
```
The compiled output is located in:
`dist/DialuxIFCBridge/DialuxIFCBridge.exe`

---

## 📋 Compatibility

| Software | Version | Compatibility |
| :--- | :--- | :--- |
| **DIALux evo** | 8.x, 9.x, 10.x, 11.x, 12.x, 13.x, 5.14+ | ✅ 100% (No Pro subscription needed) |
| **Autodesk Revit** | 2018 - 2027 (IFC Export) | ✅ Native export supported |
| **ArchiCAD** | 22 - 28 | ✅ Full IFC support |
| **Tekla Structures** | All IFC exports | ✅ Supported |
| **BlenderBIM / FreeCAD** | All versions | ✅ Supported |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). Free for both commercial and personal use.
