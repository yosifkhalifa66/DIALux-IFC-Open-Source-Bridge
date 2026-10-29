# Native DIALux Object Inventory

## Status and evidence boundary

This is an evidence-led inventory for DIALux evo 14.0 / ProjectData and ImportIfc
assemblies 5.14.0.5 installed at `C:\Program Files\DIAL GmbH\DIALux`. The
interfaces and implementation type signatures below were inspected locally.
This is an unsupported, version-specific API, not a public DIALux contract.

The v1.3 workspace contains no saved `.evo` oracle and no Pro-bridge output. Its
native writer creates a site, building, storeys, room contours/spaces, and
workplanes; architectural OBJ/MTL and optional DXF remain separate files. The
actual school IFC is available at
`D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc` (6,943,553
bytes), but the installed IFC importer has not yet been run on it in this
inventory. Accordingly, importer builder signatures are evidence that DIALux
has native construction paths, not proof that every IFC entity is accepted or
that a save/reload retains each object as expected.

Field markers:

- **Observed**: present in current bridge code, an installed DIALux signature,
  or a reflected importer implementation.
- **Constant**: currently supplied as a fixed bridge default; not a claim that
  DIALux requires that value.
- **Unknown**: the installed API reflection did not establish the value,
  persistence, or behavior. Do not silently substitute a guessed value.

Confidence scores estimate confidence in each inventory statement, not
confidence that the corresponding IFC conversion already works.

## Current bridge output

| Output | Observed content | IFC identity | Status |
|---|---|---|---|
| Native `.evo` | Site, building, storeys, one storey element per level containing room contours, spaces, and workplanes | IFC GlobalIds are not embedded in DIALux objects. Adjacent `_room_audit.json` maps each native room contour/storey to its IFC GlobalId; source storey IDs are not yet mapped. | Native rooms/levels and contour-associated storey elements are implemented; IFC wall/slab/opening conversion is not |
| OBJ/MTL | Per-element triangulated geometry, grouped by IFC storey/category, with material assignments | GlobalIds are written to the metadata sidecar and used in OBJ object names | Separate reference geometry, not native building objects |
| JSON sidecar / room CSV | IFC names, classes, storey, property data, geometry/material metadata, room schedule and boundary data | GlobalIds retained for indexed/exported IFC entities | Data sidecar only |
| Architecture inventory JSON | Wall/opening/filling/assembly relationships and world/project-frame bounds for inventoried architectural classes | GlobalIds, STEP IDs, source type, host, filling, and aggregate links recorded | IFC-derived inventory; not native DIALux objects |
| DXF | Optional 2D underlay | No native DIALux object relation established | Optional separate export |
| Pro bridge output | No local output file or project found in the v1.3 workspace | Unknown | Must not infer its native object inventory from its name or marketing |

## DIALux native/importer inventory

The `Dialux.ImportIfc` implementation exposes `BuildingBuilder`,
`StoreyBuilder`, `SpaceBuilder`, `StoreyElementBuilder`, `WallBuilder`,
`FloorSlabBuilder`, `RoomElementBuilder`, `FillingBuilder`,
`GenericGeometryElementBuilder`, `ArbitraryGeometryBuilder`, and opening
strategies. The following table separates observed APIs from unresolved runtime
behavior.

| IFC concept / DIALux carrier | Parent / attachment | Observed fields and geometry | Units / frame | GlobalId | Confidence |
|---|---|---|---|---|---:|
| Site | Project/site | `ProjectOperations.CreateSite`; current bridge sets location, latitude, longitude and timezone. Placeholder location is a bridge constant when IFC geolocation is absent. | Geographic angles are radians in the native API; current bridge converts IFC degrees to radians. Building coordinate system is `CoordSys3D`. | Not carried from `IfcSite` by the current native plan. Importer persistence unknown. | 0.99 for current bridge API; 0.65 for importer behavior |
| Building | Site | `CreateEmptyBuilding(site, coordSys, name, description)`; current bridge uses `CoordSys3D.Default` and the IFC project name. | Native helper supplies meter coordinates; exact importer transform after import remains to be verified. | Current bridge does not carry the IFC building GlobalId. Importer exposes `CreateGuidFromIfcGuid` and an IFC-object callback. | 0.99 API / 0.75 identity |
| Storey / level | Building | `CreateEmptyStorey(building, height, coordSys, name, description)`; current bridge uses geometry-derived elevation and height. | Current bridge passes meters and reads `WorldCoordSys.Origin.Z`; IFC importer accepts explicit length and angle factors. | Current bridge does not carry the IFC storey GlobalId. Importer persistence unknown. | 0.99 API / 0.70 identity |
| Room / space / contour | Storey | `AddInnerContour` accepts 2D points, utilization profile, workplane settings, text/ceiling/wall/floor materials; returns a storey contour with an associated `ISpace`. Current workplane height defaults to 0.85 m (**Constant**). | 2D contour in the storey/project coordinate frame; bridge currently rebases X/Y and storey elevation separately. Room height semantics in DIALux remain unverified. | Current native `RoomPlan` omits GlobalId even though the sidecar has it. | 0.99 API / 0.95 existing readback |
| Walls / storey construction element | Storey | `StoreyElementParams` exposes contour parameters, material, automatic outer contours, and outer-contour offset. `WallBuilder` returns representation parameters, wall contours, and a coordinate system; `StoreyElementBuilder` combines wall geometry and storey contours. No standalone `IWall` type was found in the inspected API. | Importer has length/angle factors and local coordinate systems; exact field units and persisted frame need a save/reload test. | Importer has `CreateGuidFromIfcGuid` and `OnProjectDataObjectForIfcObjectCreated`; per-wall persistence is unverified. | 0.90 for native path; 0.55 for one-to-one wall identity |
| Floors / slabs | Storey or other spatial-structure parent | `IFloorSlab` exists; `FloorSlabBuilder.ImportSlab` accepts IFC and DIALux parents and opening/filling data. Reflected params include polygon-based (`points` or `length`/`width`) and contour-based forms with height and top/bottom/side materials. `ShellBasedFloorSlabParams` accepts `ISurface3DParams`, material, flags, and IFC entity label. `SpatialStructureOperations.CreateBuildingWithMultipleStoreys` creates native floors/ceilings from a storey-wide polygon and slab thickness. A synthetic project read back native `IFloorSlab` entries after save/reload; direct conversion of individual IFC slabs remains unverified. | Length conversion factor is present in importer parameters; the synthetic polygon uses meters. Shell-based surface semantics and arbitrary triangle-mesh acceptance are unknown. | Importer has an IFC GUID conversion path; GlobalId persistence on generated slabs unverified. | 0.99 for synthetic native creation / 0.10 for IFC mapping |
| Doors/windows/openings/fillings | Opening host / element | `BuildingOpeningParams` exposes building element, geometry parameters and instance-cutout geometry; creates a product prototype and an instance under an `IElement` host. `CutoutOnBuildingOpeningStrategy` and `CutoutOnRelatingElementStrategy` are present. `FillingBuilder` handles related filling elements. | IFC length/angle factors and insertion coordinate systems are present; opening offsets and dimensions after conversion need a round-trip test. | Importer GUID callback exists; host/filling identity relationship after reload is unknown. | 0.85 for opening workflow / 0.55 for resulting public types |
| Ceilings / `IfcCovering` | Storey or room | `RoomElementBuilder.ImportCoveringAsCeiling` exists; room-element operations create suspended ceilings. Exact contour/height/material fields from IFC were not verified. | Conversion factor present; exact native coordinate frame unknown. | Importer identity mapping exists; persistence unknown. | 0.75 |
| Columns, beams, ramps and steps | Room or storey spatial structure | `RoomElementOperations` has native insert/drop operations for beams, rectangular/round columns, ramps and steps. `RoomElementBuilder` has room-element and arbitrary-building-element paths. | APIs take dimensions, materials, spatial parent and world/local coordinate systems. Exact IFC-to-primitive mapping and units require runtime test. | Importer GUID callback exists; per-object persistence unverified. | 0.80 for available primitives / 0.50 for IFC mapping |
| Furniture, proxies, stairs, railings, equipment, other represented products | Spatial-structure parent selected by importer | `GenericGeometryElementBuilder` and `ArbitraryGeometryBuilder` create representation parameters for IFC products. The inspected geometry strategies include bounding boxes, extruded area solids, shells, and boolean operations. Exact class allow-list and public DIALux object type are unknown. | Explicit IFC length/angle factors and local coordinate systems exist. Raw triangle-mesh acceptance is unknown. | Importer GUID callback exists; persistence must be tested. | 0.70 for generic geometry path / 0.40 for class coverage |
| Unsupported/2D/MEP products | None established | `IfcImport.NotImportableIfcProductIds` and `NotSupportedIfcTypeFiltering` exist. The exact filtered product classes and reasons were not enumerated. | N/A | Product entity labels are reported by the import API; GlobalId association is not guaranteed for rejected entities. | 0.95 that rejected IDs can be reported / 0.30 for specific class rules |

## Field-level evidence

### Observed in the current native writer

- Site creation uses DIALux norm defaults. If IFC coordinates are absent, the
  current label `"IFC import location"` is a bridge constant, not a detected
  real location.
- Building creation uses a default coordinate system and project name.
- Storeys have a name, height, and coordinate system whose Z origin is the
  selected room-floor elevation after subtracting the shared export origin.
- Rooms are created from 2D inner contours. The workplane height is 0.85 m
  unless configured otherwise.
- A neighboring `_room_audit.json` retains each room's IFC GlobalId, source
  and native storey, transformed contour, selected geometry source, and
  geometry warnings. This is an external traceability map; the DIALux room
  itself does not yet retain the IFC GlobalId after save/reload.
- Current names are normalized for DIALux, but original names and GlobalIds
  remain in sidecars.
- The DIALux room object does not embed its IFC GlobalId. The adjacent audit
  sidecar preserves a room-to-ID mapping, but this external mapping is not
  equivalent to identity persisted on the native object. IFC GlobalIds for
  native storeys/buildings are not yet included. Do not claim full native-object
  traceability until persistence is proven against the DIALux API.
- Native API save/reload readback (experiment 008) shows that the current room
  creation path creates one `IStoreyElement` per level. Its contours associate
  with each room: 108/108 in the school IFC. This is storey-level contour
  construction, not one-to-one native IFC walls. The tested project contained
  zero standalone `IFloorSlab` floors/ceilings and zero enumerated
  `IRoomMainSurfacesElement` objects; visual and lighting-calculation semantics
  remain unknown.
- Floor-slab reflection (experiment 009) found polygon-, contour-, and
  shell-based parameter types. Although the concrete DIALux `Storey`
  implementation exposes `CreateFloorSlab`, the host also exposes a
  `CreateBuildingWithMultipleStoreys` service operation. A synthetic project
  created through that service retained native floor slabs after save/reload.
  This does not yet show how to create a slab on the existing room-based
  storeys or map a particular IFC `IfcSlab`; do not count these test slabs as
  part of the production package pipeline.
- `<model>_architecture_inventory.json` captures exact IFC void/fill and
  aggregate/nest relationships. For the school IFC, 158 hosted openings link
  to 138 door/window fillings; 25 curtain-wall parents decompose into 1,205
  represented `IfcPlate`, `IfcMember`, and `IfcDoor` components. This sidecar
  inventories source data but does not create those products in the `.evo`.
- The inventory attempts tessellation bounds for all inventoried native-tier
  classes. In the school IFC, 2,305/2,344 products produced bounds; the other
  39 are identified by IFC GlobalId and warning reason. A bound is not an
  exact construction profile, material, or native-object mapping.

### Observed in the installed DIALux IFC importer

- `IIfcImportFactory.CreateIfcImport(FileInfo)` creates an IFC import request;
  `IIfcImport.DoImport()` performs it. `SelectedIfcObjects` and
  `NotImportableIfcProductIds` expose selection and rejection information.
- The importer exposes building/storey/space, wall/storey-element, floor-slab,
  room-element, filling/opening, and generic/arbitrary-geometry builders.
- Import parameters include explicit length and angle unit factors.
- Importer methods include `CreateGuidFromIfcGuid` and
  `OnProjectDataObjectForIfcObjectCreated`; it also has an IFC property-set
  builder. These prove that GUID/property-set integration exists in the
  implementation, but do not prove every generated object keeps its source
  GlobalId after save/reload.
- Two opening strategies exist: cutout on the building opening and cutout on
  the relating element. Which is selected for each IFC source pattern is not
  yet verified.

## Transform status

OBJ, optional DXF, native room contours, and native storey elevations now use
the same immutable `CoordinateTransform`. It carries source-unit scale, origin
offset, output-unit scale, additional scale, and rotation; exporters do not
recompute their own origin or rotation. A focused known-point test covers OBJ,
DXF, and native room coordinates.

The app's native-project package workflow chooses the XY origin from the center
of selected room-footprint bounds instead of the first exported mesh vertex.
The Z origin remains zero. The user confirmed that the model and room geometry
now align correctly in DIALux after placement. This is a visual desktop
confirmation, not a measured residual or save/reload test; see
`experiments/003-room-centered-origin.md`.

The full school IFC run retained 52,198 OBJ vertices and 89,096 triangles and
produced 89,096 DXF faces. The first corresponding triangle compared from the
OBJ and DXF files had zero coordinate delta. The same transform was passed to
native room/storey planning, which produced 64 Level 1 rooms at 0 m and 44
Level 2 rooms at 3.9624 m. See
`experiments/002-shared-transform.md` for the measurement and limitations.
There is no SVG exporter, so SVG alignment is not implemented or validated.

The transform gate passes for the outputs available today, and the reported
desktop XY placement issue is visually resolved in the user's DIALux run.
Numeric alignment tolerance, save/reload behavior, and behavior on other IFCs
remain unverified.

## Import-path and fallback decisions

1. The installed DIALux IFC import implementation is the primary oracle and
   likely native-construction route. It should be exercised before recreating
   its object field/geometry logic in bridge code.
2. The importer is version-specific and its implementation is not a public API.
   The current bridge host is .NET 8; loading the installed importer
   implementation required a .NET 10 diagnostic host because it references
   `System.Collections.Immutable` 10. This is an integration constraint, not
   proof that production invocation is impossible.
3. Until a save/reload import run establishes support, do not claim that a
   standalone wall, door, window, furniture object, or raw mesh is accepted.
   Report rejected/unknown entities through `NotImportableIfcProductIds` when
   the official importer is exercised.
4. No generic OBJ fallback should silently replace native objects. Unsupported
   object classes need an explicit report with their IFC GlobalIds and reason.
5. The Pro bridge inventory and any vendor-authored native `.evo` project are
   still unknown because neither artifact is available locally.

## Open questions

1. What exact IFC classes become each DIALux native class in a real import?
2. Are walls persisted as individual objects or combined storey construction?
3. Which opening strategy is used for doors/windows, and does each opening
   remain linked to its host after reload?
4. Which IFC materials and reflectance/transmittance fields survive import?
5. What complexity/object-count limits cause omissions or slowdowns?
6. Can the installed importer be invoked headlessly through its module factory,
   or must it run inside DIALux's UI process?
7. Can a saved project be automatically opened and checked for import errors?

## Evidence confidence

| Claim | Confidence |
|---|---:|
| Current bridge creates native sites/buildings/storeys/room contours/spaces | 0.99 |
| Installed 5.14.0.5 IFC importer has native wall, slab, room-element, opening/filling, and generic-geometry builder paths | 0.97 |
| The exact IFC-to-DIALux class mapping is known from signatures alone | 0.20 |
| Every imported native object retains an IFC GlobalId after save/reload | 0.35 |
| The importer accepts arbitrary mesh geometry as a first-class native object | 0.25 |
| A Pro bridge output/object inventory is available in this workspace | 0.05 |
