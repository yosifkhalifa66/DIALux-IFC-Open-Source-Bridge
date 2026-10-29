# 010 - Lighting parity workflow start

## Status

In progress. Lighting calculation parity has not been measured; the manual DIALux reference (project, screenshots, surface data, calculation results) is not present in this workspace. Native room generation and geometry alignment are verified for the school IFC (Tier A candidate identified). This experiment starts the workflow as specified in the user instructions.

## Scope

- Use `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- Tier A baseline: room `STORAGE` (GlobalId `1kgiVvwHP9p95wDipag4gZ`), Level 1, floor_z_m 0.0, height_m ~2.743 m, rectangular 4-point contour
- Follow phases 1-10; log runs one variable changed at a time

## Current state (verified)

- IFC loads: 108 rooms, 6 storeys (2294 products)
- STORAGE extracted via `DialuxStfExporter.extract_rooms()`: valid contour, no geometry warnings in current extraction
- Native export (`DialuxNativeProjectExporter`) creates `.evo`, verifies via native host, writes `*_room_audit.json` (all pass in tests)
- OBJ/MTL + architecture inventory export path intact; shared `CoordinateTransform` used across exporters
- All 51 core tests pass

## Test set plan (initial)

From school IFC, select candidates by tier:

| Tier | Criteria | Candidate (to confirm) |
|---|---|---|
| A (simple) | rectangle, no openings apparent | STORAGE (`1kgiVvwHP9p95wDipag4gZ`) - baseline |
| B (moderate) | L/U shape, doors/windows likely | To be selected after inspection of room shapes/openings |
| C (complex) | columns/beams/glazing/obstructions | School IFC shows 0 IfcColumn/IfcBeam in inventory per exp 007; may need different IFC |
| D (multi-room/multi-level) | corridor + rooms, stacked levels | Corridor rooms on multiple levels exist |

## Controls (to fill when manual reference exists)

| Control | Value |
|---|---|
| DIALux evo version/build | Unknown (user reports v14) |
| Luminaire (product/file/version) | TBD |
| Luminaire count/pos/rot/mounting height | TBD |
| Maintenance factor | TBD |
| Working plane height/edge offset/grid | TBD |
| Calculation surfaces | TBD |
| Reflectances (floor/wall/ceiling) | TBD |
| Daylight | Off (first pass) |
| DIALux license/edition | TBD |

## Next actions

1. Build experiment log structure for runs (phase 8). Create `experiments/011-parity-run-template.md` or use inline logging.
2. Create comparison helper script to record geometry metrics from room audit + plan vs reference (phase 5 scaffolding).
3. When manual reference is provided: create run entry with single variable change, capture diffs, triage per phase 7.
4. Fix bugs as discovered; ensure fixes are general (not room-specific).
5. Continue building test set from school IFC where possible.

## Notes

- No `IfcRelSpaceBoundary` in school IFC; opening attribution is heuristic only.
- Native adapter requires DIALux 14.0 / ProjectData 5.14.0.5.
- OBJ underlay is separate from native `.evo` rooms; calculation geometry source needs to be verified when testing (open question 3).
- DIALux calculation/result export automation unknown (open question 1).
