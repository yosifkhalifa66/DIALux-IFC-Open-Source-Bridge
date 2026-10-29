# 012 - School IFC tier candidates

Source: `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc` (108 rooms, 6 storeys). No IfcRelSpaceBoundary records; opening attribution is heuristic only.

## Tier A (simple) - rectangle, no obvious openings
Candidate from earlier: STORAGE `1kgiVvwHP9p95wDipag4gZ` (Level 1, ~14.87 m² body area, 4-point contour) - baseline.

Other rectangular/simple candidates found:
- RECEPTION `1kgiVvwHP9p95wDipag4_i` (Level 2, 4 points, rect-like)
- ELECTRICAL `0dVLQ3BYj4zOvRKQxLIQzh` (Level 1, 5 points, rect-like)
- VEST. `0oFoRhwXr3ShGDxv90QE2q` (Level 1, 4 points, rect-like)
- COUNSELOR rooms (Level 2, 6 points, rect-like)
- JNTR. rooms (4 points, rect-like)
- MECHANICAL `2sjkBoyf5A7wp1gPBvaBX_` (Level 1, 4 points, rect-like)
- Utility `2QZySdU$XFqvU7mdAsuZws` (Level 2, 4 points, rect-like)

## Tier B (moderate) - L/U shape or with doors/windows
Many CLASSROOMs are 6-8 point polygons (non-rectangular) - likely L or complex shapes. Also WORKROOM, RESOURCE rooms etc.

## Tier C (complex) - columns/beams, multiple openings, sloped/high ceiling, open-plan edge, glazed wall
Exp 007 notes school IFC has no columns/beams; glazing/curtain walls exist in inventory but may not be native openings in DIALux room model. Open-plan corridors are large/complex.

## Tier D (multi-room/multi-level)
Corridors span levels; full building export creates native storeys/rooms (verified - 2 storeys, 108 rooms). Corridor rooms had elevation reassignment warnings which were handled.

## Notes
- Room geometry extraction uses body floor mesh with fallback to IFC FootPrint; warnings logged where mismatches occur.
- Native project creation groups by storey, validates elevations, reassigns misleveled rooms when matching verified storey exists.
- All rooms export successfully in full building test.
