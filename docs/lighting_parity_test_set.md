# Lighting parity test set

## Purpose and status

The manual DIALux room is the reference. A room passes only after geometry and
calculation results are compared under one recorded control sheet. Candidate
rooms below are **not reference builds** and no parity claim is earned yet.
The user confirmed on 2026-10-28 that the model and rooms now align correctly
in DIALux. The placement check is visually passed; numeric residual and
lighting-calculation parity have not been measured.
IFC-only geometry analysis and full native-project save/reload verification
have since been completed; see `experiments/005-school-ifc-geometry-audit.md`.
The absence of a manual photometric reference does not block those IFC-side
workflow steps.

The main room-parity corpus is included in this project:

- `testdata/ifc/MEP-Elementary-School-Architectural.ifc`
- Revit 27.3.0.28, IFC2X3, imperial source units
- 108 IfcSpaces; 108 IfcDoors; 48 IfcWindows
- No `IfcRelSpaceBoundary` records, so IFC does not explicitly associate
  openings with rooms. Door/window proximity is only a geometry heuristic.
- No IfcColumn or IfcBeam instances were found.

The project also includes `testdata/ifc/sample_office.ifc`, a small IFC4 geometry
fixture with one storey and no `IfcSpace`, doors, or windows. It cannot serve as a
room-lighting parity case. The school IFC is enough to start representative
same-source tests, but not enough for
the requested 8-12-room, multi-authoring-tool robustness set.

## Candidate room set

Areas and heights are extracted from IFC geometry. A “nearby opening” count
means its tessellated centroid falls within 0.5 m of the room footprint and
its Z range overlaps the room; it is **not** a verified room-opening relation.

| # | Tier | IFC room | GlobalId | Storey | Area | Height | Observed features | Candidate status |
|---:|---|---|---|---|---:|---:|---|---|
| 1 | A | STORAGE | `1kgiVvwHP9p95wDipag4h1` | Level 1 | 6.38 m² | 3.81 m | Four-corner rectangle; no nearby door/window by centroid heuristic | Best simple-room candidate |
| 2 | A* | CORRIDOR | `1kgiVvwHP9p95wDipag4gx` | Level 2 | 97.85 m² | 9.19 m | Eight-corner footprint; no nearby door/window by centroid heuristic; unusually tall | Alternate geometry control; not ordinary Tier A |
| 3 | B | CLASSROOM | `129eYbcVLFLejyskxLKN7E` | Level 1 | 51.74 m² | 2.74 m | Nine-corner extracted footprint; one nearby door and one nearby window by centroid heuristic | Representative classroom |
| 4 | B | CLASSROOM | `1kgiVvwHP9p95wDipag4_U` | Level 2 | 51.74 m² | 2.74 m | Same general classroom shape; one nearby door and one nearby window by centroid heuristic | Cross-level repeat |
| 5 | B | KITCHEN | `1kgiVvwHP9p95wDipag4gh` | Level 1 | 147.50 m² | 3.66 m | Eight-corner footprint; five nearby doors, no nearby windows by centroid heuristic | Irregular/opening case |
| 6 | C | GYM | `1kgiVvwHP9p95wDipag4gd` | Level 1 | 801.17 m² | 10.62 m | Large open room; two nearby doors and eight nearby windows by centroid heuristic | High/open space |
| 7 | C | LIBRARY | `1kgiVvwHP9p95wDipag4gz` | Level 1 | 199.52 m² | 9.73 m | 15-corner extracted footprint; six nearby doors, no nearby windows by centroid heuristic | Irregular/high space |
| 8 | C | CORRIDOR | `1W_beoIsDALf_c5f2B9AnA` | Level 1 | 208.74 m² | 13.33 m | 41-corner extracted footprint; 11 nearby doors, no nearby windows by centroid heuristic | Complex geometry; confirm whether valid lighting room |
| 9 | C | CORRIDOR | `1kgiVvwHP9p95wDipag4hN` | Level 1 | 174.23 m² | 3.96 m | 50-corner extracted footprint; 24 nearby doors, no nearby windows by centroid heuristic | Complex/obstruction proxy; confirm room semantics |
| 10 | D | Corridor + 3 rooms + stacked-level repeat | `1kgiVvwHP9p95wDipag4gv`, `129eYbcVLFLejyskxLKN7E`, `129eYbcVLFLejyskxLKN7G`, `129eYbcVLFLejyskxLKN7I`, plus Level 2 `1kgiVvwHP9p95wDipag4_U` | Level 1 + Level 2 | Multi-room | 2.74 m rooms; corridor height varies in export | Level 1 corridor footprint is within 0.102 m of each selected classroom; upper-level classroom provides stacked-level comparison | Candidate spatial cluster; verify manually |

*Tier A denotes a simple footprint candidate only. Candidate #2's unusually
tall room volume makes it unsuitable as a normal-room lighting baseline.*

This gives ten room test cases from one real IFC, but not ten independent
buildings or authoring-tool robustness samples. The adjacency is geometric
proximity only: the source has no `IfcRelSpaceBoundary` records, and centroid
opening attribution is not a host/room relationship. Tier C candidates include
high/complex geometry but no IfcColumn/IfcBeam elements exist in this source.
The Tier D cluster includes one upper-floor room, not a fully validated
corridor-plus-three-rooms on both levels.

## Per-room reference record

Candidate #1, `STORAGE` (GlobalId `1kgiVvwHP9p95wDipag4h1`), is the Tier A
geometry baseline: the IFC-derived contour is valid and rectangular, with area
6.383959 m² and height 3.81 m. Candidate #2 is an alternate geometry case
only; its 9.19 m height is atypical. The source IFC has no space-boundary
relations, so neither the centroid heuristic nor host-wall links prove that a
specific door/window belongs to a room.

For each selected room, record before tool comparison:

- IFC path, schema, authoring tool/version, room name and GlobalId
- source storey, floor elevation, room height, measured floor area
- wall/floor/ceiling dimensions and reflectances
- opening count, areas, type, sill/head heights, and how the source relation was verified
- obstructions and their dimensions/positions
- manual DIALux build time, project path, screenshot path, and exported surface data

Manual reference project files, screenshots, surface data, and build times
have not been supplied. The v2.5 exporter has now created and reload-verified a
108-room native DIALux project from the included school IFC; see experiment
015. The 12 selected GlobalIds have paired blank measurement forms under
`testdata/results/elementary-school-v2.5-canonicalized/parity-inputs/`.
Calculation parity still needs matched manual and generated DIALux calculations
because the IFC contains no lighting results or luminaires.

Use `experiments/004-tier-a-reference-baseline.md` to capture the first
reference build. Keep the IFC source, DIALux project, screenshots, export
reports, and a record of the exact selected room together; do not compare
results until reference and generated cases use identical controls.

## Shared calculation control sheet

Fill these once from the manual reference and use the exact same values for
every tool run. A blank entry is unknown, not a default.

| Control | Recorded value |
|---|---|
| DIALux evo version/build | Version 14 reported by user; exact build to record |
| Licence/edition used for tests | Not recorded |
| Luminaire file/product, count, position, mounting height, rotation | Not recorded |
| Maintenance factor | Not recorded |
| Workplane height and edge offset | Bridge default workplane is 0.85 m; reference value not recorded |
| Calculation grid and calculation surfaces | Not recorded |
| Floor/wall/ceiling reflectance | Must be set explicitly; not recorded |
| Daylight | Off for first pass |

## Run log

No manual-reference or calculation-parity run has been completed. Add one
experiment entry per changed variable under `experiments/` before accepting a
conversion change.
