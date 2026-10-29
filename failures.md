# Verification status and remaining limits

## Verified in v2.5

- All 57 unit tests pass with the supplied Python environment.
- All Python source files compile.
- The project owner manually tested v2.5 and confirmed that it works. Visual and tessellation issues were observed and are deferred to the next version.
- Windows app bundle and Inno Setup installer compile against DIALux evo 14 project-data assemblies 5.14.0.5.
- Native adapter self-test saves and reopens a two-level `.evo` project with four room-boundary contours associated with four spaces and one generic mesh.
- The included elementary-school IFC exports 108 rooms across Level 1 and Level 2. Native save/reload verification confirms all 108 room contours remain associated with the 108 spaces, plus 2,385 generic IFC mesh objects representing 355,942 triangles. The separate OBJ reference model and architecture inventory also export.
- Parity template generation and CLI incomplete-result behavior were exercised. Blank measurements/control data correctly produce `INCOMPLETE`.

## Product and data limits

- Lighting parity has not been measured. No manual DIALux reference result or generated-project calculation data has been recorded.
- The native project adds individual source products as generic mesh objects; it does not create parametric DIALux wall/slab/door/window products. These meshes currently use a default wall material, and their effect on DIALux calculation behavior has not been validated. The test IFC contains no `IfcLightFixture`; fixture geometry in other files would be a mesh, not a DIALux photometric luminaire.
- The IFC contains a room assigned to a modeling-reference storey whose floor geometry matches Level 2. v2.5 now resolves this before storey filtering. Two corridor rooms also have large body-floor versus IFC FootPrint differences and must be reviewed before they are used as parity cases.
- The 108-room school is one IFC corpus. The small IFC4 office sample has no `IfcSpace`, doors, or windows and supports geometry-export checks only.
- The native school conversion reports two unsupported grid products; they remain listed as package warnings. The architecture inventory separately reports 39 tessellation omissions for objects without usable representations.
- The installer was compiled, but not installed, upgraded, or removed on a clean machine. The installer is unsigned.

## Open work after v2.5

1. Create the manual DIALux reference for the selected GlobalIds using the recorded controls in `docs/lighting_parity_workflow.md`.
2. Add the same luminaire and controls to the generated `.evo` project, calculate the selected rooms, and enter measured values into the paired templates.
3. Investigate the two corridor footprint warnings before using those rooms as reference cases.
4. Install, launch, upgrade, and uninstall the setup executable on a clean supported Windows system.
5. Review DIALux licensing and distribution terms and sign the installer before broad public distribution.
