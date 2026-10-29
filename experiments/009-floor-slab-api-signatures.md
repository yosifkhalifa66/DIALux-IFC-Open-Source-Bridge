# 009 - Native floor-slab API signature inventory

## Hypothesis

The installed DIALux API may provide a deterministic polygon or contour route
for creating native floor slabs, even though the current saved bridge projects
contain none.

## Variable changed

No bridge behavior changed. Extended a temporary reflection probe to inspect
floor-slab-related types and methods in the installed DIALux 14.0 assemblies.

## Observed signatures

Installed ProjectData version 5.14.0.5 exposes:

- `ProjectObjectType.FloorSlab`.
- `PolygonBasedFloorSlabParams` constructors accepting either:
  - polygon points, height, and top/bottom/side materials; or
  - length, width, height, and top/bottom/side materials.
- `StoreyContourBasedFloorSlabParams` with contour collection,
  `ContoursDefineFloorSlab`, height, top/bottom/side materials, and
  `DisableSubtraction`.
- `ShellBasedFloorSlabParams` accepting a list of `ISurface3DParams`, material,
  shell flags, and IFC entity label; it also exposes height and separate
  top/bottom/side material properties.
- The concrete `Dial.Dialux.ProjectData.InstanceObjects.Storey` implementation
  has `CreateFloorSlab(IPolygonBasedFloorSlabParams)`, returning `IFloorSlab`.
- `IFloorSlab` is a native building element with storey association, height,
  outer contours, and material properties.

The host-accessible
`SpatialStructureOperations.CreateBuildingWithMultipleStoreys(...)` API also
accepts an outer polygon, storey count, building height, floor-slab thickness,
and ceiling/wall/floor materials.

## Synthetic save/reload proof

Added a diagnostic `slab-test` mode to the native host and created a disposable
project using the service operation above. The single-variable test inputs
were an 8 m x 6 m polygon, two storeys, 6.0 m total building height, and 0.2 m
floor-slab thickness. DIALux created two storeys at 0 m and 3 m, each reported
with a 2.8 m height.

The project was saved and reopened with the native host's `inspect` mode. The
readback retained `IFloorSlab` instances:

| Storey | Floors | Ceilings |
|---|---:|---:|
| Storey 1 | 1 | 1 |
| Storey 2 | 1 | 0 |

The floor/ceiling listing includes three entries. `"Ground element 2"` appears
as Storey 1's ceiling and Storey 2's floor; whether these entries refer to one
shared slab object was not tested. Temporary `.evo` output was removed after
inspection.

## Decision

Keep the diagnostic mode: a supported spatial-structure service call creates
native `IFloorSlab` objects that survive save/reload. This proves an available
native slab creation route for a regular, storey-wide polygon. It does not
prove that this is a suitable route for irregular or independently modeled IFC
slabs. The current production room pipeline still creates no floor/ceiling
slabs.

The shell-based parameter is the only inspected signature that directly takes
surface geometry; whether its surface types can represent the IFC tessellation
without changing meaning is unknown. A room-contour slab would be a different
geometry strategy and must be benchmarked separately rather than conflated
with exact `IfcSlab` conversion. Next, compare one IFC `IfcSlab`'s source
geometry and placement against a native slab created from its footprint, then
validate save/reload and identify whether the DIALux API can preserve its
GlobalId and material assignments.

## Confidence

- The listed signatures exist in the installed DIALux assemblies: **0.99**
- The host-accessible multi-storey service creates native floor slabs:
  **0.99**
- The synthetic slabs survive save/reload: **0.99**
- The native slabs are geometrically equivalent to an arbitrary IFC `IfcSlab`:
  **0.10**
- These signatures are available as a stable public extension contract: **0.20**
- Either route produces geometry used as expected in lighting calculations:
  **0.00**
