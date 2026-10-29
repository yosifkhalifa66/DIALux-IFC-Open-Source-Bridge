# 016 - Native Room Boundary Creation and Save/Reload Verification

## Goal

Make native DIALux room boundaries a required, reported part of the generated
project instead of checking only room and level names.

## Implementation

- Each selected `IfcSpace` footprint is passed to DIALux `AddInnerContour` and
  associated with a native `ISpace` on its source level.
- The native host readback now reports storey elements, boundary contour
  counts, boundary-to-space association counts, floor/ceiling slabs, and room
  opening counts.
- Python save/reload validation requires at least one native contour per room
  and exactly one associated native space per input room. Missing or broken
  boundaries fail the export instead of reporting a complete native project.
- The room audit and completion dialog report the verified native boundary
  counts.

## Verification

- DIALux evo 14 / ProjectData 5.14.0.5 self-test created and reloaded one
  building, two storeys, four spaces, four native boundary contours, and zero
  openings. Storey elevations and room elevations remained aligned.
- Python regression coverage checks both a complete contour-to-space readback
  and a missing association failure.
- This is room-boundary generation from IFC spaces. It is not one-to-one IFC
  `IfcWall` conversion and does not yet create doors/windows, arbitrary IFC
  slabs, or luminaires as native DIALux products.

## Rejected slab experiment

The reflected `Storey.CreateFloorSlab` method belongs to an internal concrete
implementation not exposed by the `IStorey` instances available to this host.
Setting `IStorey.FloorThickness` created no slabs and shifted a storey in the
synthetic readback, so that route was removed. No floor-slab behavior is
enabled in production. The separate `slab-test` path remains a known synthetic
building service probe and is not part of IFC conversion. The rejected setter
probe output `testdata/results/native-floor-slab-selftest.evo` is retained only
as evidence of that failed experiment; do not use it as a production sample.

## Decision

Keep the verified native room-contour path and its strict readback checks.
Continue with the installed IFC importer or a supported native element API for
IFC walls, slabs, openings/fillings, and luminaires; do not substitute bounds
or guessed room-level geometry and label it as exact IFC construction.
