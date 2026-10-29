# 013 - Test set initialization

## IFC under test
- `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
- IFC2X3, Revit 27.3.0.28, imperial source units
- 108 IfcSpaces, 108 IfcDoors, 48 IfcWindows
- No IfcRelSpaceBoundary

## Selected test rooms (initial candidates)

### Tier A
1. STORAGE - GlobalId `1kgiVvwHP9p95wDipag4gZ`, Level 1, rect-like 4-point contour, ~14.87 m² body area, height ~2.743 m (from extraction). Verified native export works.

### Tier B
2. CLASSROOM rooms - non-rectangular (6-8 points), likely L-shape or complex. Good candidates for moderate complexity.
3. WORKROOM/RESOURCE - multi-point contours.

### Tier C
4. Large open rooms/corridors - complex geometry. Note: no columns/beams in this IFC per exp 007.

### Tier D
5. Multi-storey set - full building export verified (2 storeys, 108 rooms). Use for multi-room/multi-level testing.

## Status
- Room extraction working
- Native project creation working for single rooms and full building
- Room audit generation working
- Coordinate transforms shared and verified
- All tests passing

## Next
- Wait for manual DIALux reference builds with control sheet filled
- Run tool on same rooms with identical controls
- Compare per phase 5
- Log each run per phase 8
