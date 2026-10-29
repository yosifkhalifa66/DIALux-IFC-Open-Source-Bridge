# 001 - Native API inventory

## Hypothesis

The installed DIALux IFC importer already contains native builders that can
serve as the authoritative object/geometry oracle, avoiding invented project
object types and fields.

## Variable changed

No conversion variable or production behavior changed. The installed
`Dialux.ImportIfc` assembly was inspected with a temporary diagnostic host
targeted to .NET 10 because the importer references
`System.Collections.Immutable` 10. The diagnostic command has been removed
from the production native host.

## Corpus and evidence

- Installed DIALux evo 14.0 ProjectData and ImportIfc assemblies, version
  5.14.0.5.
- DIALux IFC Bridge v1.3 source and current native project writer.
- School IFC available at
  `D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`
  (6,943,553 bytes). It was **not imported** during this API inventory.
- No `.evo` oracle or Pro-bridge output was found in the v1.3 workspace.
- The workspace is not a Git repository; no commit is available.

## Results

- Reflected 62 IFC-related DIALux API types and 17 importer builder/strategy
  types.
- Confirmed `IIfcImportFactory.CreateIfcImport(FileInfo)`,
  `IIfcImport.DoImport()`, `SelectedIfcObjects`, and
  `NotImportableIfcProductIds`.
- Found native construction paths named `WallBuilder`,
  `StoreyElementBuilder`, `FloorSlabBuilder`, `RoomElementBuilder`,
  `FillingBuilder`, `BuildingOpeningParams`,
  `GenericGeometryElementBuilder`, and `ArbitraryGeometryBuilder`.
- Found two opening/cutout strategies and an IFC GUID conversion/object
  callback.
- No IFC model conversion or save/reload test was run, so there are no before /
  after geometry metrics and no evidence of exact class mappings or persistent
  GlobalIds.

## Decision

Keep the evidence and use the DIALux importer as the first native-object oracle.
Do not implement guessed IFC-to-project-data mapping yet. Next experiment:
exercise the installed importer on the school IFC in a disposable project,
read back native object types/placements/GlobalIds, and record rejected IFC
entity IDs. This workspace has no Git commit mechanism; no production
conversion code was retained from this experiment.

## Confidence

- Native builder APIs exist in the installed version: **0.97**
- The importer can create all desired IFC object classes: **0.20**
- The importer can be invoked headlessly from the current helper: **0.30**
- Every imported object retains its IFC GlobalId after reload: **0.35**
