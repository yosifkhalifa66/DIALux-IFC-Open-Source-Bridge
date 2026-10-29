# DIALux IFC Bridge 2.5

DIALux IFC Bridge converts selected IFC storeys, room boundaries, and represented building products into a native DIALux evo project. It also exports an OBJ/MTL reference model and audit sidecars.

## What it produces

- A native `.evo` project with a site, building, levels, room contours, and per-product IFC mesh objects grouped by storey.
- A separate OBJ/MTL architectural reference model.
- DXF room geometry and JSON sidecars for room and architecture traceability.
- A package status manifest reporting completed steps, warnings, or errors.

The native `.evo` creates a DIALux storey boundary contour for each selected IFC room and associates every contour with its native calculation space; the exporter checks these associations after save/reload. Represented IFC products such as walls, slabs, doors, windows, and furniture are added as separate native DIALux generic geometry mesh objects and checked after reload. Their IFC GlobalIds, types, storeys, and triangle counts are recorded in the room audit. These objects are tessellated meshes, not parametric DIALux wall/slab/window/door objects. IFC surface materials are not mapped to verified DIALux reflectance or transmittance values. IFC light-fixture geometry can be included as a mesh, but it is not a photometric DIALux luminaire and provides no imported luminaire data. Unsupported products are listed in `package_status.json`. The native adapter uses DIALux evo project data assemblies from an installed DIALux evo version compatible with the pinned API (5.14.0.5). The build does not redistribute DIALux assemblies.

## Requirements

- Windows 10/11, 64 bit.
- DIALux evo installed for native project creation.
- The packaged build includes the .NET 8 runtime for its native adapter.

For development, install `requirements.txt`. To create the Windows bundle, install `requirements-build.txt`, .NET SDK 8, DIALux evo, and Inno Setup 6, then run:

```powershell
python build_exe.py
```

Set `DIALUX_INSTALL_DIR` if DIALux is installed outside its standard location. The application bundle is written to `dist/DialuxIFCBridge`; the setup executable is written to `release/` when Inno Setup is available.

## Use

Run `main.py` from a development checkout or launch `DialuxIFCBridge.exe` from the installed bundle. Select an IFC file, review detected levels and rooms, choose an output folder, and start export. Native IFC mesh creation is enabled by default and can be turned off in BIM Conversion Settings. Keep the OBJ and MTL sidecar together if you need the separate reference model.

After export, inspect `package_status.json` in the output folder. A `PARTIAL` status means some deliverables were not produced; warnings and error details are included in that file and the application log. Do not treat partial outputs as a complete package.

## Evidence and limits

The v2.5 build was verified with a 108-room, two-level IFC2X3 school model. Native save/reload verification confirmed 108 room contours and 2,385 generic geometry elements representing 355,942 triangles; two unsupported grid products were reported. The IFC model is not redistributed in this repository or release archive. This single corpus does not establish broad IFC compatibility or lighting-calculation parity with a manually authored DIALux project.

Lighting parity requires measured data from both a manual DIALux reference and the generated DIALux project, using the same recorded luminaire, calculation, and material controls. The comparator in `tools/lighting_parity_compare.py` marks missing measurements as incomplete, rejects mismatched controls, and does not invent results. See `docs/lighting_parity_workflow.md`, `docs/lighting_parity_test_set.md`, and `experiments/` for the protocol and evidence.

## Verification for this v2.5 rebuild

The native adapter's two-level self-test, including a generic mesh, and the 108-room IFC project's two-level native output were saved and reload-verified. All 57 unit tests pass. The project owner manually confirmed that the v2.5 build works; visual and tessellation issues are deferred to a future version. Lighting parity remains incomplete pending matched measured DIALux runs. Parametric architectural elements, verified native material mapping, photometric luminaire import, and clean-machine installer validation remain outstanding. See `failures.md` for details.

## Troubleshooting

- If native project creation cannot find DIALux, install evo or set `DIALUX_INSTALL_DIR` during development/build.
- If IFC geometry is invalid or unsupported, review the application log and the package status manifest; no deliverable should be assumed complete after a failure.
- Include the relevant log and `package_status.json` when reporting a reproducible issue. Do not include proprietary IFC data unless permitted.

## License

See `LICENSE`. DIALux evo and its assemblies remain subject to their own license terms.
