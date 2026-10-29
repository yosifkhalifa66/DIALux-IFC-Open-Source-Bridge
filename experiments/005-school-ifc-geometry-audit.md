# 005 - Full school IFC geometry and native-room audit

## Status

IFC-only audit completed on 2026-10-28. No manual-reference values were used.
The same full-building IFC was used for room extraction, native-plan creation,
and DIALux save/reload verification. This validates room geometry ingestion
and native room/storey generation; it does not establish lighting-calculation
parity or native architectural-object creation.

## Source and variable

- IFC: `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- Size: 6,943,553 bytes
- Schema: IFC2X3
- Authoring application: Autodesk Revit 27.3.0.28
- Source length unit: foot; conversion `0.3048 m / source unit`
- One shared transform, origin at selected room bounds center:
  `(25.7081723156, -11.9854233681, 0) m`
- Rotation: 0 radians; output units: metres
- One code-path variable changed after the initial comparison: room-level
  diagnostics for disagreement between body floors, IFC `FootPrint`s, and
  assigned storeys are now recorded in the native room audit. The chosen
  contour and transform algorithms were not changed.

## IFC inventory

The bridge indexed 2,294 products across 16 supported categories. These are
indexed categories, not a count of every `IfcProduct` in the file.

| IFC class | Count | Initial lighting tier / evidence |
|---|---:|---|
| IfcWall | 47 | Tier 1 candidate |
| IfcWallStandardCase | 290 | Tier 1 candidate |
| IfcSlab | 31 | Tier 1 candidate; floor/roof usage needs semantic inspection |
| IfcCovering | 96 | Tier 1 candidate; covering type distinguishes ceiling/floor |
| IfcDoor | 108 | Tier 1 opening/filling candidate |
| IfcWindow | 48 | Tier 1 opening/filling candidate |
| IfcFurnishingElement | 240 | Tier 2 candidate |
| IfcBuildingElementProxy | 79 | Tier 2 or Tier 3; inspect actual geometry/use |
| IfcStair | 2 | Tier 2 candidate |
| IfcStairFlight | 4 | Tier 2 candidate |
| IfcRailing | 6 | Tier 2 candidate |
| IfcCurtainWall | 25 | Tier unresolved; likely needs glazing/opening-aware handling |
| IfcMember | 864 | Tier unresolved; IFC class alone does not establish beam vs other member |
| IfcPlate | 331 | Tier unresolved; IFC class alone does not establish slab/panel role |
| IfcRoof | 15 | Tier unresolved for room-level lighting occlusion |
| IfcZone | 0 | Not present |
| IfcColumn / IfcBeam | 0 | Not present; this corpus cannot validate those mappings |

These are conservative tier candidates, not an implemented per-element
conversion policy. The IFC class is not enough to assign every `IfcMember`,
`IfcPlate`, covering, or proxy to a lighting role. No guessed classification
was silently promoted to a native object.

### Openings and host relationships

- `IfcOpeningElement`: 158
- `IfcRelVoidsElement`: 158; all 158 opening elements have a relating host.
- `IfcRelFillsElement`: 138
- Door fill links: 90 of 108 doors; those are hosted by 15 `IfcWall` and 75
  `IfcWallStandardCase` instances.
- Window fill links: 48 of 48 windows; those are hosted by 22 `IfcWall` and
  26 `IfcWallStandardCase` instances.
- 18 doors have no `IfcRelFillsElement` link; 20 voided openings have no
  filling relation.
- `IfcRelSpaceBoundary`: 0.

Therefore the IFC provides exact door/window-to-opening-to-wall relations for
138 fillings, but it does not authoritatively associate those objects with
rooms. Room-level opening counts/areas must not be inferred from proximity and
reported as IFC relationships.

## Room geometry results

- Extracted `IfcSpace` rooms: 108; all have an IFC GlobalId.
- Invalid/empty footprints: 0.
- Extractor's same-storey footprint-overlap validation: passed.
- All 108 room contours were transformed with the same shared transform used
  by the OBJ/native export path.
- IFC `FootPrint` representations exist for 59 of the 108 rooms. In 58, the
  selected contour agrees with the `FootPrint` to numerical precision; the
  remaining selected body contour differs by 41.01% of the footprint area.
- Comparing raw bottom-surface geometry with available `FootPrint`s exposed
  two additional significant outline conflicts. Both are explicitly warned
  and included with the selected source/elevations/areas in the native-room
  audit sidecar; geometry selection remains deterministic and is not silently
  changed to force a match.
- Contour vertex-count distribution:
  - 4 vertices: 20 rooms
  - 5: 6
  - 6: 34
  - 7: 15
  - 8: 10
  - 9: 4
  - 10: 2
  - 11: 4
  - 14: 1
  - 15: 4
  - 16: 1
  - 19: 1
  - 25: 1
  - 41: 1
  - 46: 2
  - 50: 1
  - 54: 1

| Source assignment after geometry analysis | Rooms | Total footprint area | Floor Z range | Height range |
|---|---:|---:|---:|---:|
| Level 1 | 64 | 3,990.7066 m² | 0.0000 m | 2.7432–13.3272 m |
| Level 2 | 43 before reassignment | 1,966.8701 m² | 3.9624 m | 2.7432–9.1944 m |
| Volume Modeling Reference 2 | 1 before reassignment | 227.4894 m² | 3.9624 m | 9.3272 m |

The single room assigned to `Volume Modeling Reference 2` has a footprint at
3.9624 m, matching Level 2. The native planner logged and reassigned it to
Level 2; the resulting native project has 64 Level 1 rooms and 44 Level 2
rooms. One Level 2 room's body floor was at 0 m, but its valid IFC `FootPrint`
was at 3.9624 m; the extractor used that footprint and logged the correction.

The audit also identifies a separate corridor assigned to
`Volume Modeling Reference 2`: body floor 3.9624 m, IFC `FootPrint` 6.0960 m,
source storey elevation 9.6520 m. Neither elevation matches the IFC storey.
Its body outline is 227.4894 m² and its footprint outline is 385.6398 m²
(41.01% symmetric difference using the larger outline as denominator). The
body-floor contour is retained because it matches the Level 2 floor geometry;
the planner moves it to Level 2 and the report flags the mismatch for review.
This room is an explicit hostile-file exception, not a verified ordinary
lighting room.

A second Level 2 corridor (`1kgiVvwHP9p95wDipag4gx`) has a 48.85% difference
between its raw body-floor outline and `FootPrint`. The body floor is at 0 m;
the `FootPrint` is at the assigned Level 2 elevation 3.9624 m, so the exporter
selects the footprint and warns about the contour disagreement.

## Representative source measurements

| Room | GlobalId | Storey | Area | Height | Contour vertices |
|---|---|---|---:|---:|---:|
| STORAGE | `1kgiVvwHP9p95wDipag4h1` | Level 1 | 6.383959 m² | 3.8100 m | 4 |
| CORRIDOR | `1kgiVvwHP9p95wDipag4gx` | Level 2 | 97.847587 m² | 9.1944 m | 8 |
| CLASSROOM | `129eYbcVLFLejyskxLKN7E` | Level 1 | 51.739897 m² | 2.7432 m | 9 |
| CLASSROOM | `1kgiVvwHP9p95wDipag4_U` | Level 2 | 51.739897 m² | 2.7432 m | 6 |
| KITCHEN | `1kgiVvwHP9p95wDipag4gh` | Level 1 | 147.497085 m² | 3.6576 m | 8 |
| GYM | `1kgiVvwHP9p95wDipag4gd` | Level 1 | 801.171427 m² | 10.6195 m | 10 |
| LIBRARY | `1kgiVvwHP9p95wDipag4gz` | Level 1 | 199.515922 m² | 9.7252 m | 15 |
| CORRIDOR | `1W_beoIsDALf_c5f2B9AnA` | Level 1 | 208.743955 m² | 13.3272 m | 41 |
| CORRIDOR | `1kgiVvwHP9p95wDipag4hN` | Level 1 | 174.227843 m² | 3.9624 m | 50 |

These measurements describe IFC-derived contours, not independent manual
measurements. The unusually high room volumes are preserved as source
geometry; this audit did not normalize them.

## Native project save/reload verification

The current native exporter created a temporary `.evo`, then reloaded and
inspected it through the version-pinned DIALux adapter:

| Check | Result |
|---|---|
| Native project saved | Pass |
| Native project reloaded | Pass |
| Native storeys | 2 |
| Level 1 rooms / elevation | 64 / 0.0000 m |
| Level 2 rooms / elevation | 44 / 3.9624 m |
| Reloaded room floor elevations | All equal their native storey elevation |
| User-visible XY placement | User confirmed model and rooms align in DIALux |
| Numeric XY residual / save-reopen in GUI | Not measured |
| IFC GlobalIds in native audit sidecar | 108 of 108 rooms; 108 unique IDs |
| Geometry review warnings | 3 warnings across the two corridor cases |
| Audit room names | 108 unique names, matching native creation order |

The temporary `.evo` was removed after the readback check. The DIALux adapter readback verifies names, counts, storey elevations, and
room-floor elevations. The adjacent `<project>_room_audit.json` records all
108 source GlobalIds, native room names/storeys, transformed contours, and
geometry warnings. GlobalIds are an external mapping; they are not embedded
inside DIALux room objects. The adapter does not verify each saved contour's
area, material reflectance, or opening host.

## Decision and next experiment

1. Keep the shared room-bounds-centered transform; the full native project
   round-trips and the user confirmed the model aligns with rooms in DIALux.
2. Keep the current room/storey correction behavior; the misassigned
   reference-level room is assigned by matching floor geometry and logged.
3. Use the actual IFC host relationships for wall/opening experiments. Do not
   label room proximity heuristics as relationships.
4. Next, establish an IFC-only native opening/wall inventory against DIALux's
   own import path, then verify saved object classes and placements. The
   current bridge's native output still contains rooms/storeys, not native
   architectural walls/openings.
5. Lighting-result parity remains untested: an IFC has no DIALux Eavg/U0/UGR
   results, and the current adapter does not generate a calculation.

## Confidence

- Room extraction and polygon validity for this IFC: **0.99**
- Native level/room count and elevation save/reload: **0.99**
- User-confirmed visual XY alignment: **0.90** (no numeric residual)
- Door/window-to-wall links directly read from IFC relations: **0.99**
- Room-level opening attribution from IFC: **0.00** (no space boundaries)
- Native wall/opening creation in the bridge: **0.00** (not implemented)
- Lighting calculation parity: **0.00** (not measured)
