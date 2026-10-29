# Changelog

## 2.5.0 — released

- Establishes explicit v2.5 versioning across the application and exports.
- Makes package completion and partial failures visible in `package_status.json`.
- Stages and verifies native project output before replacing final deliverables.
- Resolves rooms assigned to a non-matching IFC storey before filtering the selected levels.
- Requires native room-boundary contour-to-space associations to survive save/reload and reports those counts in the UI/package status.
- Makes lighting parity comparison evidence-driven; absent metrics remain incomplete instead of being filled with assumed values.
- Adds paired reference/generated measurement templates with exact control-sheet matching and room GlobalId scoping.
- Clarifies that native DIALux room spaces and OBJ architectural context are separate outputs.
- Adds selected IFC products as per-product native DIALux generic mesh objects, preserving storey placement and IFC identity in the audit.
- Adds reload verification for every native mesh object and records mesh/triangle counts and skipped products.
- Adds a UI switch for native IFC mesh generation, enabled by default.
- Verifies 2,385 native IFC mesh objects and 355,942 triangles alongside all 108 school room contours in the reloaded project.
- Updates the interface copy to describe the actual output and its limitations.
- Compiles the Windows application bundle and 2.5.0 installer; validates the native adapter with a saved and re-opened two-level sample project.
- Runs the included 108-room IFC through OBJ, architecture inventory, and native project export; save/reload verification confirms 108 room contours and 108 associated spaces.

The project owner manually confirmed that the 2.5 build works. Visual and tessellation issues are known and deferred to a later version. Lighting parity and the technical limits in `failures.md` remain open.
