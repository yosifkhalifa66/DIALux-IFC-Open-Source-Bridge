# 004 - Tier A geometry baseline and reference plan

## Status

The IFC-derived room geometry baseline is complete and recorded in
`005-school-ifc-geometry-audit.md`. No manual DIALux reference project,
screenshot, or lighting calculation has been supplied. This does not block
continued IFC geometry, transform, classification, or native save/reload work;
it only means calculation-parity metrics cannot yet be compared.

## Room under test

- Tier: A
- IFC: `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- Room: `STORAGE`
- GlobalId: `1kgiVvwHP9p95wDipag4h1`
- Source candidate area: 6.38 m2
- Source candidate height: 3.81 m
- Source storey: Level 1
- Candidate footprint: four corners
- Nearby opening count: zero by centroid-distance/Z-overlap heuristic only;
  manually inspect the IFC/DIALux view before declaring this a no-opening case.
- IFC geometry status: extracted; valid four-corner polygon
- DIALux native save/reload: included in the full-building verification in
  experiment 005; native room count/elevations verified
- Lighting calculation reference: not available in the IFC; parity not claimed

## Hypothesis

The IFC-derived rectangular room contour can be reproduced by the native
project plan with the shared coordinate transform. Lighting-result parity is a
separate, unverified claim.

## Variable changed

None. This is the first baseline, not a tuning run. Record all controls before
calculation. If any control must change later, create a new numbered experiment
and change only that variable.

## Optional DIALux lighting-reference procedure

1. Use the IFC and bridge room schedule to identify the room by name and
   GlobalId; do not treat nearby-opening heuristics as room-boundary relations.
2. Build only this room manually if lighting calculation parity is being
   measured. Record elapsed hands-on build time and the
   exact geometry/surface settings; do not infer missing values from defaults.
3. Save the native DIALux project and capture a plan view and a 3D view.
4. Set the shared calculation controls below explicitly, calculate with
   daylight disabled, and capture/export the calculation results and grid.
5. Run the bridge for the same room and settings, save the generated project
   and report, then reproduce the exact calculation controls and luminaire
   arrangement. Do not adjust the generated geometry to make the result match.
6. Record measured geometry and result differences. Explain failures by
   geometry evidence; leave unavailable metrics marked unknown.

## Shared controls (fill from the actual reference)

| Control | Observed value |
|---|---|
| DIALux evo version and build | Version 14 (user-reported); exact build unknown |
| Licence/edition | |
| Luminaire product and photometric file/version | |
| Luminaire count | |
| Luminaire coordinates, rotation, and mounting height | |
| Maintenance factor | |
| Working-plane height | |
| Working-plane edge offset | |
| Calculation grid spacing and surfaces | |
| Floor reflectance | |
| Wall reflectance | |
| Ceiling reflectance | |
| Daylight disabled | Required for first pass; verify and record |

## Evidence and results (fill after the run)

| Evidence/metric | Manual reference | Bridge-generated | Difference / status |
|---|---|---|---|
| Project file path | | | |
| Plan screenshot path | | | |
| 3D screenshot path | | | |
| IFC/model report path | | | |
| Manual build time | | | |
| Floor area (m2) | | | Target: <1% difference |
| Room height (m) | | | Record measured difference |
| Wall area (m2) | | | Target: <3% difference |
| Openings (count and area) | | | Exact count; area <5% |
| Obstruction positions | | | Record; no obstruction expected only after verification |
| Eavg (lx) | | | Target: <3% difference |
| U0 | | | Target: <5% difference |
| UGR | | | If used; target within 1 |
| Luminaire count | | | Must match exactly |
| Import/calculation warnings | | | Must be recorded |
| Overall decision | | | Geometry baseline passed at IFC/native-plan level; calculation parity pending |

## Limitations

- The recorded area, height, and opening classification are IFC-derived
  candidates, not verified DIALux measurements.
- The source IFC has no `IfcRelSpaceBoundary`; opening-room attribution is not
  authoritative.
- DIALux UI operations and manual reference measurements require the licensed
  desktop application. No automated parity result is asserted here.
