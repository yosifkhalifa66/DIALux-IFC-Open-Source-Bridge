# 017 — Native IFC product meshes

## Question

Can IFC products be included in a DIALux native `.evo` alongside the existing native building, storeys, room contours, and spaces?

## Implementation

The DIALux 5.14.0.5 host creates one `IGenericGeometryElement` per represented IFC product, attached to its assigned selected storey. IfcOpenShell tessellates the product geometry; the shared project transform and IFC unit scale are applied before surfaces are passed to DIALux. Openings are omitted as standalone solids because wall/body tessellation already applies IFC opening subtractions. Source GlobalIds and types are stored in the room audit. Each requested mesh object's presence is verified after saving and reloading the `.evo`.

The interface enables this by default and supports disabling it for large/diagnostic exports. Unsupported geometries are written to `package_status.json` and shown as notices.

## Verified result

Input: `testdata/ifc/MEP-Elementary-School-Architectural.ifc` (IFC2X3).

- 108 rooms and 108 native room-boundary contours across Level 1 and Level 2.
- 2,385 native generic geometry objects survived save and reload.
- 355,942 mesh triangles were inserted.
- Two grid products did not tessellate and were reported as warnings.
- Result: `testdata/results/native-mesh-school-v25-verified.evo`.
- A separate native host self-test mesh also survived project save and reload.

## Limits

These are DIALux generic mesh objects, not parametric DIALux walls, slabs, doors, or windows. The current host assigns the default wall material to each mesh; IFC material and optical properties are not mapped. A mesh for an IFC light fixture is not a DIALux photometric luminaire. Lighting calculation behavior and parity have not been verified. The 2,385-element result is one corpus, not broad IFC compatibility evidence.
