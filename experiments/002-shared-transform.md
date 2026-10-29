# 002 - Shared coordinate transform

## Hypothesis

Using one immutable IFC-world-to-project transform for OBJ, DXF, and native
room planning will remove the prior DXF/OBJ origin mismatch without changing
mesh counts or room/storey placement.

## Variable changed

Introduce and pass one `CoordinateTransform` through OBJ export, optional DXF
export, and native room/storey planning. It carries source-unit scale, local
origin, output-unit scale, additional scale, and rotation. No exporter applies
its own origin subtraction or XY rotation. STF room alignment accepts the same
transform for compatibility, although STF is not the primary project workflow.
There is no SVG exporter in this workspace.

## Corpus and run

- Full school IFC:
  `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
  (6,943,553 bytes).
- Output selections: all default OBJ categories/storeys; space volumes omitted.
- Run performed after the transform changes. Temporary OBJ/DXF outputs were
  removed after measurement.
- Workspace is not a Git repository; no commit is available.

## Metrics

| Metric | Before | After |
|---|---:|---:|
| Indexed products | 2,294 | 2,294 |
| Extracted rooms | 108 | 108 |
| OBJ vertices | 52,198 | 52,198 |
| OBJ triangles | 89,096 | 89,096 |
| Elements without geometry | 39 | 39 |
| DXF faces | 89,096 | 89,096 |
| DXF vs OBJ first triangle coordinate delta | DXF unrebased; not aligned | `(0, 0, 0)` for all 3 vertices |

OBJ origin offset: `(22.2029723156, 7.7638019399, 0.0)` m. The first exported
triangle in both OBJ and DXF was `[(0, 0, 8.4328), (0, 0, 0), (-42.672, 0, 0)]`
in project metres. The same source triangle was compared, rather than the
unrelated first `v` record and first DXF face vertex.

Native planning reused the same transform and produced:

- Level 1: elevation `0.0` m, 64 rooms.
- Level 2: elevation `3.9624` m, 44 rooms.

The room extractor reported one room whose body floor disagreed with its
assigned storey; it selected that room's IFC `FootPrint` at the storey
elevation. A misassigned room group at 3.9624 m was merged into the matching
verified native level. Both decisions were logged.

## Decision

Keep the shared-transform implementation. Full-corpus mesh counts are
unchanged, the previously world-coordinate DXF is now rebased, and the same
triangle agrees exactly between OBJ and DXF. Native room/storey planning uses
the same origin/rotation/unit conversion. Focused cross-output tests also
exercise a known point across OBJ, DXF, and a native room contour.

The transform gate passes for the outputs currently implemented. SVG is not
implemented and therefore remains unverified. This experiment does not validate
DIALux save/reload behavior or native architectural objects.

## Confidence

- OBJ and DXF share the same transform for the tested school IFC: **0.99**
- Native room/storey plan uses the same transform: **0.95**
- Correct north/rotation transfer from IFC into DIALux: **0.30**
- SVG alignment: **0.00** (no SVG exporter exists)
