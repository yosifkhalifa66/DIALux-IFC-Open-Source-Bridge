# 003 - Room-centered project origin

## Hypothesis

DIALux may place pasted OBJ geometry relative to its model insertion origin
rather than preserve the file's assumed `(0, 0, 0)` in the same way as the
native `.evo` geometry. The previous transform used the first tessellated OBJ
vertex as its origin, which is an arbitrary point on an arbitrary first
element. Centering the shared local project frame on the selected room
footprint bounds makes the native room set centered at `(0, 0)` and gives
DIALux a stable, meaningful project anchor.

This is a testable import-anchor hypothesis, **not yet a proven explanation**
of the user's observed XY offset at the time this experiment began. The user
has since confirmed that the model and room geometry align correctly in
DIALux; the transformation still applies equally to OBJ and native rooms.

## Variable changed

Only the origin anchor changes for the app's package workflow:

- Before: first exported geometry vertex.
- Candidate: center of the selected room-footprint XY bounds; Z origin remains
  zero so storey elevations are preserved.

The unit scale, rotation, categories, room geometry, mesh tessellation, and
native project contents remain unchanged. The chosen basis and offset are now
recorded in the transform metadata and completion dialog.

## Corpus and run

- Full available real corpus: Revit 27.3.0.28 school IFC at
  `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`.
- Source has 108 rooms across two geometry-confirmed levels and no explicit
  IfcRelSpaceBoundary relationships.
- Other IFCs/manual DIALux projects are not currently available in the
  workspace.
- Full-corpus OBJ, DXF, and native-project generation completed with the
  candidate transform. The saved `.evo` reloaded and verified 108 rooms across
  two levels.

| Metric | Previous first-mesh-vertex anchor | Room-bounds-center candidate |
|---|---:|---:|
| IFC products | 2,294 | 2,294 |
| Extracted/native rooms | 108 | 108 |
| Native levels | 2 | 2 |
| OBJ vertices | 52,198 | 52,198 |
| OBJ triangles | 89,096 | 89,096 |
| Elements without geometry | 39 | 39 |
| DXF faces | 89,096 | 89,096 |
| Origin X/Y (m) | `(22.202972, 7.763802)` | `(25.708172, -11.985423)` |
| Transformed room-bounds center (m) | `(3.505200, -19.749225)` | `(0, 0)` |
| Transformed OBJ-bounds center (m) | `(3.200400, -22.007176)` | `(-0.304800, -2.257952)` |

The OBJ is centered close to, but not exactly on, the room bounds because the
architectural geometry extends beyond the room footprints. This is a geometric
difference, not evidence that the files disagree. The OBJ/DXF triangulation
counts are unchanged. The native levels reload at 0 m and 3.9624 m.

## DIALux placement result

On 2026-10-28, the user confirmed that the model and room geometry now align
correctly in DIALux after placement. This closes the visual XY placement check
for the room-centered transform. No screenshot, measured residual, or saved
before/after project was supplied, so this is not a quantified tolerance or a
save/reload validation.

## Decision

Keep the room-bounds-centered origin. The user-confirmed DIALux placement is
consistent with the candidate fixing the reported visible XY shift. Do not
add a compensating XY constant. Retain the saved transform and sidecar bounds
for future regression runs. Lighting calculation parity, exact residual,
save/reload behavior, and use with other IFCs remain unverified.

## Confidence

- One shared transform still applies to OBJ and native rooms: **0.99**
- Room-bounds center is a more meaningful project anchor than first mesh vertex: **0.90**
- The room-bounds-centered model and room geometry visually align in the user's DIALux run: **0.90** (user-confirmed; not independently measured)
- Alignment residual is within a numeric tolerance: **unknown** (no measured residual)
- Save/reload preserves the alignment: **unknown**
