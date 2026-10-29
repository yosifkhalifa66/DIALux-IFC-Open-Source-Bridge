# 008 - Native storey contour and room association readback

## Hypothesis

The bridge's native room creation may already produce DIALux building
construction associated with the room spaces, even though no one-to-one
native wall objects are yet created from IFC wall products. Inspect the
installed DIALux object graph before designing a separate wall conversion.

## Variable changed

No geometry, selection, transform, or room creation behavior changed. Extended
the native helper's save/readback JSON to report DIALux `IStoreyElement`
objects, their contours and associated spaces, storey floors/ceilings, and
per-room main-surface/opening counts.

## Corpus and results

Installed DIALux evo 14.0 / ProjectData 5.14.0.5.

### Synthetic helper self-test

Created and reloaded a native `.evo` containing four rooms on two storeys:

| Storey | Rooms | Native `IStoreyElement`s | Contours | Contour-to-space associations | Floors | Ceilings | Enumerated room-main surfaces |
|---|---:|---:|---:|---:|---:|---:|---:|
| Level 1 | 2 | 1 | 2 | 2 | 0 | 0 | 0 |
| Level 2 | 2 | 1 | 2 | 2 | 0 | 0 | 0 |

Each storey element reports two contours, and those contours resolve to both
native spaces on that level after save/reload.

### School IFC

Created and reloaded the full room project from
`D:\Electrical Projects\MEP-Elementary-School-Architectural.ifc`:

| Storey | Rooms | Native `IStoreyElement`s | Contours | Contour-to-space associations | Floors | Ceilings | Enumerated room-main surfaces |
|---|---:|---:|---:|---:|---:|---:|---:|
| Level 1 | 64 | 1 | 64 | 64 | 0 | 0 | 0 |
| Level 2 | 44 | 1 | 44 | 44 | 0 | 0 | 0 |
| **Total** | **108** | **2** | **108** | **108** | **0** | **0** | **0** |

The native project readback retained all 108 rooms and all 108 contour-to-space
associations. Temporary `.evo` outputs were deleted after measurement.

## Decision

Keep the readback diagnostics. The present `AddInnerContour` path persists one
native storey element per level, with one contour associated to each room. This
is evidence for a DIALux-native, room-contour construction path; it is **not**
evidence that individual IFC walls have been imported as individual native
objects, nor that these contours are currently used as the expected lighting
calculation surfaces.

The readback found no standalone `IFloorSlab` floors/ceilings and no
enumerated `IRoomMainSurfacesElement` objects in these saved projects. Do not
silently treat room contours as standalone slabs or claim floor/ceiling
material parity. Next, inspect the DIALux IFC importer or a real GUI-created
reference project to determine how wall faces, slabs, and openings are
represented and persisted before adding IFC-derived construction.

The external OBJ remains separate from the native `.evo`. This experiment
does not address the user's reported OBJ-to-room placement or linkage issue;
those remain explicitly deferred.

## Confidence

- DIALux save/reload retains one storey element per level in these projects:
  **0.99**
- Every room contour associates with its respective native space: **0.99**
- These contours are equivalent to one-to-one IFC walls: **0.00**
- These contours are proven calculation surfaces with expected materials:
  **0.00**
- Standalone floor/ceiling slabs were present in the tested saved projects:
  **0.00** (none were read back)
