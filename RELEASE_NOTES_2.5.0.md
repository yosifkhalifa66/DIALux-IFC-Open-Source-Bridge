# DIALux IFC Bridge 2.5.0

This release creates a native DIALux evo project from selected IFC storeys, room contours, and represented building products.

## Included

- Native site, building, storeys, spaces, and room-boundary contours.
- Native generic geometry objects created per represented IFC product and assigned to storeys.
- Shared coordinate transform across native geometry, room boundaries, and OBJ output.
- IFC identity and mesh counts in the native room audit, plus export warnings for unsupported geometry.
- A desktop UI option to include or omit native IFC meshes.
- OBJ/MTL, architecture inventory, room schedule, DXF, and parity workflow tools.

## Verification

- 57 unit tests pass.
- Native self-test mesh survives project save and reload.
- A two-level, 108-room IFC test project reloads with 108 room boundaries and 2,385 native geometry objects (355,942 triangles).
- The project owner manually tested the v2.5 build and confirmed it works.

## Known limits

Native building products are generic meshes, not parametric DIALux wall, slab, door, or window objects. IFC optical materials are not mapped to verified reflectances. IFC light fixtures do not import as photometric luminaires. Visual and tessellation issues observed during manual testing are deferred to a future version. Lighting parity has not been established.
