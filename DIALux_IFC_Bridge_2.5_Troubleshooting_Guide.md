# DIALux IFC Bridge 2.5 — Everyday Troubleshooting Guide

**For lighting designers, electrical engineers, BIM coordinators, and other daily users**  
Version: 2.5.0  
Last updated: October 2026

## What this guide helps you do

Use this guide when the Bridge cannot open an IFC, creates only some of the expected files, reports warnings, or produces a project that looks different from the source model. It is written for users of the application; it does not require Python, C#, or IFC programming knowledge.

The Bridge prepares a DIALux evo project with native room spaces and IFC building geometry represented as generic mesh objects grouped by storey. It also creates an OBJ reference export and audit files. The native objects are not parametric DIALux walls, doors, windows, or luminaires. The Bridge does not infer verified surface reflectances, photometric data, or a finished lighting design from IFC.

## Start here: five-minute diagnosis

1. **Read the exact message.** Note whether it appeared while loading the IFC, exporting geometry, creating the `.evo`, or copying files to the clipboard.
2. **Open the output package folder.** By default it is under `Documents\DialuxIFCBridge\exports`. The app also has an **Open Exports Folder** button in Diagnostics. Each run gets a new folder named like `Model_DIALux`; if that name already exists, the next run uses `_2`, `_3`, and so on.
3. **Open `package_status.json`** in that run’s folder with Notepad. Check `status`, `current_or_failed_step`, `completed_steps`, `warnings`, and `error`.
4. **Check which deliverables exist.** A missing `.evo` does not necessarily mean the OBJ and audit exports failed. Use the status and warnings to identify the failed stage.
5. **If the cause is unclear, save a troubleshooting bundle** from the app’s **Diagnostics** tab before rerunning. Keep the original IFC and the failed output package until the issue is understood.

## Understand the package status

The package folder is a record of one run. Do not assume every file will exist if a run stopped partway through.

- **`COMPLETE`** — the native DIALux project and the package preparation steps completed without recorded notices. Open the `.evo` in DIALux and inspect it before design use.
- **`COMPLETE_WITH_NOTICES`** — a native project was created, but the manifest contains warnings. Common examples are skipped IFC meshes or an unavailable clipboard handoff. Review `warnings` and visually inspect affected areas.
- **`PARTIAL`** — some package outputs were produced, but the native `.evo` project was not successfully created. The OBJ, MTL, metadata, room schedule, or architecture inventory may still be usable. Check `current_or_failed_step` and `warnings` for the native failure reason.
- **`FAILED`** — package preparation stopped before it could complete. The manifest’s `error` and `current_or_failed_step` identify the operation that failed. Earlier steps may have left usable files in the folder.
- **`CANCELLED`** — the operation was cancelled. Files from completed steps may remain; treat the package as incomplete and inspect it before using it.

`package_status.json` is written at the end of package processing. If it is missing, the app may have stopped before writing it, the output folder may be different from the one you opened, or Windows may have prevented the write. Check the app log and the troubleshooting bundle.

## Common problems and what to do

### 1. “Please drop a valid .ifc file” or the IFC does not load

**What it means:** The selected file is not recognized as an `.ifc` file, or the app could not access it.

**Try this:**

- Confirm that the file is a real IFC export and ends in `.ifc`. Changing a different file’s extension to `.ifc` does not convert it.
- Copy the file to a normal local folder such as Documents, rather than opening it from a disconnected network drive, email preview, compressed archive, or removable disk.
- Make sure the file has finished downloading and is not zero bytes. Ask the BIM author to re-export it if it is incomplete.
- Close software that may be writing or locking the IFC, then try again.
- If the file still fails, use **Diagnostics → Save Troubleshooting Bundle** and retain the exact error text.

### 2. The IFC loads, but there are no usable rooms or no `.evo` file

**What it means:** Native room creation depends on usable `IfcSpace` room geometry in the selected storeys. An IFC may contain a building shell but no spaces, or its space representations may not form valid closed room contours.

**Try this:**

- Ask the BIM author to include/export the project’s `IfcSpace` objects with valid 3D geometry and storey assignments.
- Confirm that the storeys containing those spaces are selected in the Bridge.
- If the package contains an OBJ and other sidecars but no `.evo`, open `package_status.json` and read the `warnings` entry about native room creation.
- Check room names, levels, and boundaries in the originating BIM application. Fix the IFC model there and export it again when spaces are absent, open, self-intersecting, overlapping, or assigned to the wrong level.
- If a room reports that the configured workplane is not below the room height, reduce the workplane in the Bridge’s room options or correct the room height in the IFC.

Rooms with holes in their footprint, invalid contours, or overlapping footprints on the same storey can be rejected because they cannot be represented safely as the intended native DIALux room boundaries. Do not use an incomplete room set for lighting calculations without checking it in DIALux.

### 3. “No elements match the selected categories and storeys” or an empty-looking OBJ

**What it means:** No exportable geometry matched the current filters, or matching IFC objects do not have usable 3D geometry.

**Try this:**

- Select the storeys that actually contain the elements you want.
- Enable the relevant categories (for example walls, slabs, doors, windows, columns, or furniture) in the export options.
- Check whether the IFC uses different element types or contains only spaces/2D representations.
- Retry with broader category and storey selections. If that works, narrow the selection gradually to find the filter excluding the geometry.
- Ask the BIM author to export physical elements with 3D body geometry if the model has no usable solids or meshes.

### 4. OBJ files exist but the native DIALux `.evo` is missing

**What it means:** The independent OBJ export completed, but a later native-room or native-project step failed. This is a common partial-output pattern and does not mean the entire run was lost.

**Try this:**

- In `package_status.json`, inspect `warnings` and `current_or_failed_step`. The warning often contains the direct cause.
- Confirm that the IFC has usable rooms on the selected storeys. Without room records, the Bridge cannot create its native project.
- Check DIALux evo installation and compatibility (see problem 5), then retry into a fresh output folder.
- You can still use the OBJ/MTL as a visual reference if it is present, but it does not contain the native DIALux room model. Do not treat it as a substitute for the failed `.evo` deliverable.

### 5. DIALux installation or native host/assembly errors

**What it means:** Native project creation needs a compatible DIALux evo installation and the Bridge’s native host component. Errors may mention `DIALux_x64.dll`, the native adapter/host, or an unavailable installation.

**Try this:**

- Install or repair a supported DIALux evo version using the official DIALux installer. The v2.5 native integration was developed against the DIALux evo 14 project-data assemblies; other versions may not expose the same compatible components.
- Start DIALux evo once after installation, then close it and retry the Bridge.
- If you installed the Bridge from an official package, repair/reinstall that package so its native host files are restored. Avoid downloading individual DLLs from third-party websites or copying assemblies between DIALux versions.
- If this is a managed workstation, ask IT to confirm that the Bridge and DIALux folders are not blocked by endpoint security and that your account can read/write the output folder.
- Save a troubleshooting bundle and report the exact DIALux evo version and host error if it still fails.

### 6. The output already exists or a file cannot be overwritten

**What it means:** The Bridge protects existing `.evo` projects, room audits, and inventory files from accidental overwrite. A repeated package run normally creates a new numbered package folder, but a selected standalone output file or sidecar can still collide with an existing file.

**Try this:** Choose a new output name or a new, empty folder. If you need the previous result, move or archive it yourself first. The Bridge does not require you to delete existing project work.

### 7. Some elements are missing, incomplete, or reported as skipped

**What it means:** Individual IFC products can fail geometry tessellation or have no complete finite 3D mesh. The rest of the model may still export. Warnings in the package status and architecture inventory describe skipped items where available.

**Try this:**

- Review the `warnings` in `package_status.json` and search the architecture inventory JSON for the affected element’s IFC type or GlobalId.
- Open the source IFC in its authoring application and check whether the element has a visible 3D body, valid placement, and correct storey assignment.
- Re-export the IFC from the authoring application after repairing invalid or proxy geometry.
- If many unrelated elements are skipped, retry with a smaller selection to identify whether one category or model section triggers the issue, then include the troubleshooting bundle in a support report.

### 8. Model appears too large, too small, shifted, or not aligned with rooms

**What it means:** IFC units, placements, room contours, or storey assignments may be inconsistent. The Bridge converts recognized IFC units and can center the exported coordinates on selected room bounds, but it cannot repair incorrect source coordinates or contradictory room/product placements.

**Try this:**

- Check the units declared by the IFC and compare one known dimension (for example, a 1 m doorway should be close to 1 m in DIALux).
- Keep the same selected storeys and origin/rebase option for the room and geometry exports; do not combine files produced with different options.
- Confirm that products and `IfcSpace` rooms are assigned to their actual levels and have valid placements in the source BIM model.
- Compare the `.evo` and OBJ from the same package run. Avoid mixing sidecars from different runs.
- If the source IFC itself is incorrectly scaled or positioned, correct it at source and export again. Do not compensate by guessing a scale factor for a lighting calculation model.

### 9. Rooms or building geometry look wrong in DIALux

**What it means:** A successful export means the file passed the Bridge’s checks; it does not guarantee that every source BIM convention maps perfectly to DIALux. Inspect room boundaries, levels, and mesh placement in the opened project.

**Try this:** Compare the affected room and nearby geometry with the source BIM model and the room audit sidecar. Check the source room footprint, floor elevation, height, storey assignment, and element placements. Correct the source IFC where the data is wrong; report repeatable conversion mismatches with the exact room/element identifiers and screenshots.

### 10. Materials, doors/windows, or luminaires do not behave like native DIALux objects

**What it means:** This is a product limitation, not necessarily an export error. IFC products in the native project are generic mesh objects. They are not fully reconstructed as parametric DIALux walls, slabs, doors, windows, or luminaires, and IFC material appearance is not a verified photometric reflectance mapping. Imported geometry does not provide a completed lighting calculation or electrical distribution design.

**What to do:** Use the imported model as a starting point for spatial coordination and visual reference. Review room boundaries, assign appropriate DIALux materials and reflectances, place/select photometric luminaires, configure calculation settings, and validate results in DIALux before issuing engineering deliverables.

### 11. “Clipboard is busy” or the DIALux handoff did not happen

**What it means:** The Bridge could not put the OBJ file list on the Windows file clipboard, often because another process temporarily owns the clipboard. This warning is separate from export and native `.evo` creation.

**Try this:** Close clipboard managers or apps that may be holding the clipboard and retry the handoff. Otherwise open the output folder in File Explorer and import/use the generated OBJ manually. The clipboard handoff concerns the OBJ file; it does not mean that the `.evo` project is copied into the clipboard.

### 12. Export is slow, appears stuck, or was cancelled

**What it means:** Large IFC files and detailed geometry can take time to parse, tessellate, and write. Native adapter work has a 15-minute timeout. A cancelled or timed-out package may contain outputs from completed stages only.

**Try this:**

- Allow the current stage to progress, especially for a large model, and avoid launching duplicate runs at the same time.
- If the app remains unresponsive or the native step times out, note the stage, model size, and elapsed time. Retry with fewer storeys/categories or a simplified IFC copy to isolate the expensive geometry.
- After cancelling, check the status manifest. Use a new output package for another attempt so partial output is easy to distinguish.
- If the same stage repeatedly times out on a modest model, save a troubleshooting bundle and report it.

### 13. Troubleshooting bundle or log will not open/save

**Try this:** Use the app’s **Diagnostics** tab to select **View App Log** or **Save Troubleshooting Bundle**. If a bundle cannot be saved, choose a local writable folder, ensure there is free disk space, and check Windows security software. The log is normally at `%TEMP%\DialuxIFCBridge\app.log`. If the app reports that no log exists, reproduce the issue once and try again.

## How to send a useful issue report

From **Diagnostics**, save the troubleshooting bundle. Include these details in your report:

- Bridge version (2.5.0), Windows version, and DIALux evo version.
- The exact error text and the stage shown in the app.
- The package’s `package_status.json` and a list of files that were created or missing.
- Steps to reproduce, including selected categories/storeys and room options.
- Screenshots of the source model and the corresponding DIALux result, with the affected room/element identified.
- Approximate IFC file size and whether the issue also occurs with a smaller IFC.

IFC files may contain confidential client or project information. Do not attach or publicly post the full IFC unless you have permission. The troubleshooting bundle includes logs and system information; review it for sensitive paths or details before sharing it publicly.

## Quick reference: issue to first check

- **IFC will not load:** file validity, local accessibility, exact load error, app log.
- **No `.evo`:** `package_status.json` warnings; usable `IfcSpace` rooms; selected storeys; DIALux installation.
- **Empty/missing geometry:** category/storey filters; IFC 3D body representations; tessellation warnings.
- **Wrong scale/alignment:** IFC unit, known dimensions, room/product placements, consistent options from one run.
- **Clipboard warning:** outputs may still be valid; use File Explorer and import OBJ manually.
- **Looks visually generic:** expected generic mesh representation; inspect and finish materials/lighting setup in DIALux.
- **Unclear/repeatable failure:** save a troubleshooting bundle and include the status manifest and exact reproduction steps.

---

This guide supports troubleshooting; it does not replace checking the model, calculation settings, or results against the project’s engineering requirements before use.
