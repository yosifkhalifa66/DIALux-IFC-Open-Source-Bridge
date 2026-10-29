# 014 - Building Construction vs. Object Model Strategy in DIALux evo

## Context and Objective

Explore the two architectural approaches for bringing external BIM/IFC data into DIALux evo:
1. **Constructing the Building Natively**: creating native building elements (Site, Building, Storeys, Storey Contours, Spaces/Rooms, Slabs, Openings).
2. **Making the Model as an Object inside DIALux**: placing the tessellated architectural geometry as a 3D model/furniture element inside DIALux.

This document synthesizes empirical evidence from the v1.3 native API reflection, synthetic save/reload readbacks (`experiments/008`, `experiments/009`), and the test corpus (`MEP-Elementary-School-Architectural.ifc`).

---

## 1. Native Building Construction (The `.evo` Path)

### What DIALux Exposes Natively
Inside DIALux evo 14's `Dialux.ProjectData` and `Dialux.ProjectDataService`:
- `ProjectOperations.CreateSite`: creates a site with geographic coordinates, orientation, time zone, and standard lighting norm profiles.
- `SpatialStructureOperations.CreateEmptyBuilding`: creates a building spatial container.
- `SpatialStructureOperations.CreateEmptyStorey`: creates a storey at a given Z elevation and height.
- `SpatialStructureOperations.AddInnerContour`: creates an `IStoreyElement` with a contour that associates with an `ISpace` (Room). Automatically initializes:
  - Calculation workplane (default 0.85 m elevation, 0.5 m wall zone).
  - Room text label at 0.25 m.
  - Surface material assignments (ceiling, wall, floor).
  - Utilization profile (e.g. EN 12464-1 standard office / classroom profile).
- `Storey.CreateFloorSlab(IPolygonBasedFloorSlabParams)`: creates a native `IFloorSlab` with top, bottom, and side material properties.

### Strengths of Native Construction
- Native rooms generate DIALux calculation surfaces and summary tables automatically.
- Room schedules, floor areas, per-room lux averages ($E_{avg}$), and uniformity ($U_0$) are natively available in DIALux calculation reports.
- Storey navigation in DIALux's tree view works seamlessly.

### Limitations of Pure Native Construction from IFC
- DIALux evo does not expose a standalone public or stable `IWall` class. Walls in DIALux are represented as storey element contour assemblies (`StoreyElementBuilder`), not individual arbitrary 3D solids.
- Complex architectural elements from Revit (curtain-wall mullions, double-glazed window assemblies, faceted structural columns, irregular roof profiles) cannot be converted into native DIALux parametric building elements without DIALux's proprietary licensed IFC importer.
- Creating native building elements for every tiny framing member or mullion exceeds DIALux's internal geometric constraints.

---

## 2. Making the Model as an Object Inside DIALux (The 3D Object Path)

### What DIALux Does with 3D Objects
In DIALux evo:
- Any Wavefront OBJ model can be imported as a 3D Object / scene element.
- DIALux's radiosity and raytracing engines calculate reflections off 3D objects according to the material reflectances defined in `.mtl` ($Kd$, $Ks$, $d$).
- Semi-transparent materials (e.g., glazing with $d = 0.25$) allow daylight and artificial light to pass through.

### Strengths of the 3D Object Path
- Complete visual and geometric fidelity: captures 100% of Revit/ArchiCAD architectural elements (curtain walls, structural columns, stairs, railings, furniture, complex facades).
- No geometric topology restrictions: complex meshes, non-manifold geometry, and voids render properly.
- Realistic photometric materials ($Kd$ reflectance aligned with CIE / EN 12464-1).

### Limitations of Pure 3D Object
- DIALux does not treat a plain 3D object as a "Room". Therefore, without native spaces, DIALux cannot compute per-room summary metrics ($E_{avg}$, $U_0$) or generate room-based calculation grids automatically.

---

## 3. The Unified Hybrid Architecture (Bridge v1.3 Solution)

The optimal approach combines both paradigms:

```
+-------------------------------------------------------------------------+
|                           SOURCE IFC MODEL                              |
+-------------------------------------------------------------------------+
                                    |
          +-------------------------+-------------------------+
          |                                                   |
          v                                                   v
+-----------------------------+             +-----------------------------+
|    NATIVE ROOMS & LEVELS    |             |    ARCHITECTURAL OBJ + MTL  |
|         (.evo Project)      |             |         (3D Object)         |
|-----------------------------|             |-----------------------------|
| - Site & Building Container |             | - High-detail geometry:     |
| - Storeys at verified Z     |             |   Walls, Curtain walls,     |
| - Native ISpace rooms       |             |   Windows, Doors, Columns,  |
| - Calculation Workplanes    |             |   Beams, Slabs, Furniture   |
| - Utilization Profiles      |             | - Photometric reflectances  |
+-----------------------------+             +-----------------------------+
          |                                                   |
          +-------------------------+-------------------------+
                                    |
                                    v
          +---------------------------------------------------+
          |         UNIFIED COORDINATE TRANSFORM              |
          |  Origin Anchor: (0, 0, Z) at Room-Bounds Center   |
          |  Scale: 1:1 in SI Metres                          |
          +---------------------------------------------------+
                                    |
                                    v
          +---------------------------------------------------+
          |                  DIALux evo                       |
          |  1. Opens native .evo project (rooms ready)       |
          |  2. User presses Ctrl+V (OBJ snaps into position) |
          |  3. Complete lighting calculation & visual model  |
          +---------------------------------------------------+
```

### Key Validation
- Shared transform verified: zero coordinate delta on tested geometry bounds (`experiments/002`).
- Origin anchored at room-bounds center gives visual alignment confirmed in DIALux (`experiments/003`).
- 108 rooms across Level 1 & Level 2 in `MEP-Elementary-School-Architectural.ifc` verified with full reload readback.

## Conclusion
The hybrid approach is the only approach that delivers both:
1. **Automated room calculation sheets, workplanes, and lux metrics** (via native `.evo`).
2. **Complete, accurate architectural shading and reflection geometry** (via pre-scaled, photometrically mapped OBJ/MTL).
