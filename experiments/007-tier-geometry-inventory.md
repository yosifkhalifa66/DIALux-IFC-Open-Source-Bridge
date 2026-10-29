# 007 - Geometry bounds for native-object tiers

## Hypothesis

The architecture sidecar needs transformed geometry bounds across the complete
native-object candidate set, not just walls, openings, doors/windows, and
curtain-wall components. Expanding one shared inventory pass should provide
source-linked geometry evidence for floors, ceilings, columns/beams,
furnishings, proxies, stairs, ramps, railings, and roofs without implementing
unverified DIALux object creation.

## Variable changed

Expanded `GEOMETRY_CLASSES` to cover every class in `INVENTORY_CLASSES` plus
`IfcWallStandardCase`. No classification rules, transforms, native objects,
or fallback behavior changed. Geometry errors remain attached to the element
and report warning list.

Added regression coverage proving that both `IfcColumn` and
`IfcFurnishingElement` receive transformed bounds when their IFC representations
tessellate.

## Corpus and results

- `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- IFC2X3, Revit 27.3.0.28; 108 rooms and 6 source storeys.
- 2,344 architectural/structural inventory products were tessellation
  candidates; 2,305 received valid bounds in the shared project frame.
- 39 geometry failures were explicit and attributable:

| IFC type | Candidate count | No bounds |
|---|---:|---:|
| `IfcCurtainWall` | 25 | 25 |
| `IfcRoof` | 15 | 10 |
| `IfcSlab` | 31 | 2 |
| `IfcStair` | 2 | 2 |
| All other candidate types | 2,271 | 0 |

Successful bounds by IFC type:

| IFC type | Bounds |
|---|---:|
| `IfcWall` | 47 |
| `IfcWallStandardCase` | 290 |
| `IfcSlab` | 29 |
| `IfcCovering` | 96 |
| `IfcDoor` | 108 |
| `IfcWindow` | 48 |
| `IfcOpeningElement` | 158 |
| `IfcColumn` / `IfcBeam` | 0 / 0 |
| `IfcFurnishingElement` | 240 |
| `IfcBuildingElementProxy` | 79 |
| `IfcMember` / `IfcPlate` | 864 / 331 |
| `IfcStair` / `IfcStairFlight` | 0 / 4 |
| `IfcRamp` / `IfcRampFlight` | 0 / 0 |
| `IfcRailing` | 6 |
| `IfcRoof` | 5 |

The complete inventory pass took 19.58 seconds on this machine. The OBJ,
shared transform, native room project, and inventory had already passed the
integrated package test in experiment 006. The inventory-only run outputs were
removed after measurement.

## Decision

Keep the broader bounds extraction. It materially improves source geometry
coverage with a measured 19.58-second pass and explicit, inspectable failures.
It is a geometry inventory only: no wall, slab, furnishing, or other
architectural products were added to the native `.evo` by this experiment.
This school IFC has no columns or beams, so those API mappings require
another IFC before they can be validated against real source objects.

The next conversion experiment should target a source class present here and
must prove the native DIALux object's type, transform, host/level, and
save/reload behavior. Do not equate an inventory bounding box with exact
construction geometry or lighting-material semantics.

## Confidence

- Candidate classes and counts measured from the school IFC: **0.99**
- Successful tessellation bounds: **0.99** (2,305/2,344)
- Shared project-frame transformation used: **0.99**
- Bounds alone are sufficient to create exact DIALux architecture: **0.10**
- Lighting results are equivalent to a manual DIALux build: **0.00**
