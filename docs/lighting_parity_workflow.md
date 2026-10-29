# Lighting parity workflow

## Current evidence

The IFC in `testdata/ifc/MEP-Elementary-School-Architectural.ifc` has 108 spaces and no luminaires. The v2.5 run creates a native project with 64 Level 1 rooms and 44 Level 2 rooms, plus separate architectural OBJ/MTL geometry. The native project is at `testdata/results/elementary-school-v2.5-canonicalized/elementary-school.evo`.

This project is a geometry starting point. It does not contain native architectural surfaces, lighting equipment, or calculation results. A parity result cannot be produced until a manual DIALux reference and a calculated generated-project run are both measured.

## Create measurement forms

The existing room audit is the identity source. The following selected cases come from `docs/lighting_parity_test_set.md` and span a small room, a classroom, an irregular room, a large room, a complex footprint, and a multi-room cluster:

```powershell
$audit = "testdata/results/elementary-school-v2.5-canonicalized/elementary-school_room_audit.json"
$forms = "testdata/results/elementary-school-v2.5-canonicalized/parity-inputs"
$ids = @(
  "1kgiVvwHP9p95wDipag4h1", "1kgiVvwHP9p95wDipag4gx",
  "129eYbcVLFLejyskxLKN7E", "1kgiVvwHP9p95wDipag4_U",
  "1kgiVvwHP9p95wDipag4gh", "1kgiVvwHP9p95wDipag4gd",
  "1kgiVvwHP9p95wDipag4gz", "1W_beoIsDALf_c5f2B9AnA",
  "1kgiVvwHP9p95wDipag4hN", "1kgiVvwHP9p95wDipag4gv",
  "129eYbcVLFLejyskxLKN7G", "129eYbcVLFLejyskxLKN7I"
)
$args = @("tools/lighting_parity_compare.py", "--generate-templates", $audit, $forms)
foreach ($id in $ids) { $args += @("--global-id", $id) }
python @args
```

The command creates `manual-reference.json` and `generated-project-results.json`. Each file contains the same room GlobalIds and blank measurements. Keep the IDs intact. Unknown values remain `null`; do not copy values from the other project or use target values as measurements.

## Build the matched DIALux runs

1. In DIALux evo, create a manual reference for the selected rooms. Record the exact evo version/build, license edition, luminaire article and photometric file, maintenance factor, workplane, wall-zone offset, calculation grid, ceiling/wall/floor reflectances, and daylight setting.
2. Measure each selected room's floor area, wall area, height, opening count and area, Eavg, U0, UGR if available, and luminaire count. Save the project and evidence paths/screenshots.
3. Open the v2.5 generated `.evo` project. Add the same luminaires and calculation controls to the selected rooms, calculate, and record the same measurements in `generated-project-results.json`.
4. Preserve source project files and evidence. Do not compare a geometry-only IFC audit estimate as if it were a measured DIALux wall area.

The bridge audit estimates wall area as perimeter times room height and labels that estimate. The comparison workflow expects measured wall area in both DIALux run files. Opening-to-room attribution is also not considered verified until the relationship is recorded from the actual project.

## Compare

```powershell
python tools/lighting_parity_compare.py `
  testdata/results/elementary-school-v2.5-canonicalized/elementary-school_room_audit.json `
  --reference-json testdata/results/elementary-school-v2.5-canonicalized/parity-inputs/manual-reference.json `
  --tool-results-json testdata/results/elementary-school-v2.5-canonicalized/parity-inputs/generated-project-results.json `
  --markdown
```

The comparator requires matching GlobalIds and matching populated control sheets. It reports `INCOMPLETE` when a required measurement/control is missing, `INCOMPARABLE` when controls differ, `FAIL` when a measured difference exceeds tolerance, and `PASS` only when every selected room is complete and within tolerance. Exit codes are 0 for pass, 1 for a measured tolerance failure, and 2 for incomplete or incomparable runs.

Default limits are floor area 1%, wall area 3%, room height 1%, opening area 5%, Eavg 3%, U0 5%, and UGR absolute difference 1.0. Change a tolerance only through an explicitly recorded protocol revision; preserve the original evidence.
