# 006 - IFC wall, opening, and curtain-wall relationship inventory

## Hypothesis

Use the source IFC's actual void/fill and decomposition relations as the
authoritative basis for classifying walls, openings, doors/windows, and curtain
walls. This should preserve traceability and avoid inferring relationships
from centroid proximity or treating aggregate system objects as standalone
solids.

## Variable changed

No native geometry conversion behavior changed. Add an inventory sidecar
exported alongside the package, using the existing shared coordinate
transform. It records IFC identities, source classes, spatial containment,
opening host/filling relations, aggregate/nest relations, and tessellated
bounds for walls, openings/fillings, curtain-wall assemblies, plates, and
members. Tessellation failures remain explicit warnings.

## Corpus

- `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- Revit 27.3.0.28, IFC2X3, source unit foot (`0.3048 m/unit`)
- Inventory duration: about 11 seconds on this machine.
- Output: 2,344 architectural/structural IFC entities; this includes 158
  `IfcOpeningElement`s in addition to the 2,294 products indexed by the app.
- The temporary test inventory was deleted after measuring it. Production
  package exports retain `<model>_architecture_inventory.json`.
- Ran the integrated package export with shared-transform OBJ, architecture
  inventory, native `.evo` creation, and native save/reload verification. It
  produced 52,198 OBJ vertices / 89,096 triangles, 108 rooms across Level 1
  and Level 2, and 108 unique room GlobalIds in the audit. Temporary package
  outputs were removed after verification.

## Opening/host/filling relationships

| IFC relationship result | Count |
|---|---:|
| `IfcOpeningElement` | 158 |
| Openings linked to a host via `IfcRelVoidsElement` | 158 |
| Host is `IfcWall` | 37 |
| Host is `IfcWallStandardCase` | 118 |
| Host is `IfcSlab` | 3 |
| Openings linked to a filling via `IfcRelFillsElement` | 138 |
| Filled by `IfcDoor` | 90 |
| Filled by `IfcWindow` | 48 |
| Openings with neither host nor filling | 0 |

Thus 20 hosted openings have no filling. Of 108 doors, 90 have an explicit
opening/fill relationship; 18 do not. All 48 windows are related to an
opening and host. No room-level boundary relation exists in this IFC, so the
inventory makes no room/opening attribution.

## Curtain-wall decomposition

- 25 `IfcCurtainWall` parents have `IfcRelAggregates` relationships.
- All 25 parent curtain-wall objects lack a tessellatable `IfcRepresentation`
  in this source; the inventory records this as an explicit warning.
- Together the curtain-wall assemblies contain 1,205 represented components:
  - 856 `IfcMember`
  - 331 `IfcPlate`
  - 18 `IfcDoor`
- All 1,205 component products have IFC representations, tessellate
  successfully, and receive shared-frame bounds in the inventory.
- The source names these plates `System Panel:Glazed` and members
  `Rectangular Mullion`; these names are useful evidence for a later
  curtain-system classification, but class/name alone is not proof of
  transmittance or native DIALux object semantics.
- 45 `IfcRelAggregates`/`IfcRelNests` relationships were recorded in total.

Do not emit both a non-geometric curtain-wall parent and its decomposed
components as duplicate solids. A later conversion must choose the represented
components for this source pattern or prove a native assembly operation that
does not double-count them.

## Geometry sidecar and transform

For each inventory element, the report records IFC GlobalId, STEP id, type,
name, object type, storey containment, representation presence, direct
opening/assembly relationships, and—where requested and tessellated—world
and local project-frame axis-aligned bounds in metres. The same
room-bounds-centered `CoordinateTransform` is recorded and applied.

- Geometry bounds were attempted for all selected `IfcWall`/
  `IfcWallStandardCase`, curtain-wall parents, `IfcDoor`, `IfcWindow`,
  `IfcOpeningElement`, `IfcMember`, and `IfcPlate` products.
- Geometry errors are included in each element and in the report's warning
  list; the report never treats an unsupported parent as a successful solid.
- The 25 reported geometry failures are exactly the 25 unrepresented
  `IfcCurtainWall` parents. Their 1,205 represented aggregate components have
  no tessellation warnings.

## Decision

Keep the relationship and assembly report. It provides deterministic,
GlobalId-addressable input for future wall/opening/native-object experiments
and proves that this Revit export's curtain walls are represented as panels,
mullions, and some doors rather than as one tessellated parent object.
Do not yet create native wall or opening objects: the inventory proves the
source relationships and geometry bounds, not DIALux's accepted construction
fields or post-save identity/host persistence.

The next experiment must exercise the installed DIALux import/construction
path on a minimal wall and one hosted opening/filling, then read the project
back to establish object types, placements, cutout behavior, and identity.
Only after that evidence should the IFC converter implement native walls or
fillings.

## Confidence

- IFC opening-to-host relations in the school model: **0.99**
- IFC opening-to-filling relations in the school model: **0.99**
- Curtain-wall aggregate members/panels are represented by IFC relations:
  **0.99**
- Curtain-wall component geometry tessellates: **0.99** (1,205/1,205)
- IFC class/name alone predicts lighting material/transmittance: **0.40**
- Exact room attachment of openings: **0.00** (no `IfcRelSpaceBoundary`)
- Native DIALux wall/opening creation or save/reload behavior: **0.00** (not
  tested by this experiment)
