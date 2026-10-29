# 015 — Room storey canonicalization and v2.5 IFC run

## Question

Does selecting Level 1 and Level 2 omit any IFC spaces that are assigned to an incorrect storey despite floor geometry matching one selected level?

## Input and initial result

Input: `testdata/ifc/MEP-Elementary-School-Architectural.ifc` (IFC2X3, 6,943,553 bytes). The inspector found 2,294 products, 108 `IfcSpace` instances, and six IFC storeys. The initial storey-filtered extraction returned 107 rooms: Level 1 had 64 and Level 2 had 43.

The missing space is `1kgiVvwHP9p95wDipag4wT` (`CORRIDOR`). IFC spatial containment assigns it to `Volume Modeling Reference 2` at 9.652 m, but its body-floor geometry is at 3.9624 m, matching Level 2. Filtering by the IFC containment name before running the native plan's correction dropped it.

## Change

Added `canonicalize_room_storey_assignments()` to reconcile room floor geometry against uniquely matching storey elevations before applying the user's selected-storey filter. The native model-plan builder uses the same normalization. The original IFC storey remains available in `source_ifc_storey` for provenance.

## Result

Re-extraction and plan construction now retain all 108 rooms: Level 1 has 64 and Level 2 has 44. The actual v2.5 pipeline exported 50,619 OBJ vertices and 86,122 triangles, generated the architecture inventory, created a native DIALux project with two storeys and 108 rooms, and passed save/reload verification.

Artifacts: `testdata/results/elementary-school-v2.5-canonicalized/`.

## Geometry warnings and parity status

- `1kgiVvwHP9p95wDipag4gx` (`CORRIDOR` on Level 2) body-floor and IFC FootPrint differ by 48.85%; the exporter selected the FootPrint due to its storey elevation alignment. Verify before using it for parity.
- `1kgiVvwHP9p95wDipag4wT` has a 41.01% body-floor/FootPrint difference; both its FootPrint and IFC assigned storey elevation disagree with its body floor. The body floor was retained and placed on Level 2 by the unique floor-elevation match. Verify its contour before use.
- Architecture inventory geometry reported 39 elements without usable tessellations. Those items remain warnings in the inventory.
- The included small `sample_office.ifc` is IFC4 with one storey and four walls but no spaces, doors, or windows. It cannot provide room-lighting parity cases.

The generated parity forms for 12 selected GlobalIds remain blank. The comparison correctly returns `INCOMPLETE`; no manual DIALux measurements, luminaire file, or Eavg/U0 results have been supplied. This experiment validates geometry processing and native project creation only.

## Verification

`python -m unittest discover -s tests -v`: 54 tests passed. The v2.5 native self-test and full 108-room project's reload inspection passed.
