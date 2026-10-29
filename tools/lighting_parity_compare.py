#!/usr/bin/env python3
"""Compare recorded manual DIALux references with bridge room audits.

Unknown measurements stay null and cannot produce a complete parity pass.
The audit geometry is a contour-based estimate; it does not infer openings,
photometric results, or luminaire data.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

DEFAULT_TOLERANCES = {
    "floor_area_pct": 1.0,
    "wall_area_pct": 3.0,
    "room_height_pct": 1.0,
    "opening_area_pct": 5.0,
    "eavg_pct": 3.0,
    "u0_pct": 5.0,
    "ugr_abs": 1.0,
}

REQUIRED_METRICS = ("floor_area_m2", "wall_area_m2", "height_m", "eavg_lux", "u0")
COMPLETION_METRICS = ("opening_count", "opening_area_m2", "luminaire_count")
MEASURED_FIELDS = (*REQUIRED_METRICS, *COMPLETION_METRICS, "ugr")
REQUIRED_CONTROLS = (
    "dialux_version",
    "dialux_build",
    "license_edition",
    "luminaire_article",
    "luminaire_file",
    "maintenance_factor",
    "workplane_height_m",
    "workplane_wall_zone_m",
    "calculation_grid",
    "reflectances.ceiling",
    "reflectances.walls",
    "reflectances.floor",
    "daylight_enabled",
)


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def compute_polygon_area(points: list[list[float]]) -> float:
    """Return the absolute shoelace area of a finite 2D polygon."""
    if len(points) < 3:
        return 0.0
    if any(len(point) != 2 or not all(math.isfinite(float(v)) for v in point) for point in points):
        raise ValueError("Polygon points must be finite XY pairs.")
    area = sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )
    return abs(area) / 2.0


def compute_polygon_perimeter(points: list[list[float]]) -> float:
    """Return the perimeter of a finite 2D polygon."""
    if len(points) < 2:
        return 0.0
    if any(len(point) != 2 or not all(math.isfinite(float(v)) for v in point) for point in points):
        raise ValueError("Polygon points must be finite XY pairs.")
    return sum(
        math.hypot(
            points[(index + 1) % len(points)][0] - points[index][0],
            points[(index + 1) % len(points)][1] - points[index][1],
        )
        for index in range(len(points))
    )


def summarize_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Compute only geometry directly supported by the room audit."""
    if not isinstance(audit.get("rooms"), list):
        raise ValueError("Room audit must contain a 'rooms' array.")
    rooms: list[dict[str, Any]] = []
    for index, source in enumerate(audit["rooms"], start=1):
        if not isinstance(source, dict):
            raise ValueError(f"Room audit entry {index} must be an object.")
        contour = source.get("native_contour_xy_m")
        if not isinstance(contour, list) or len(contour) < 3:
            raise ValueError(f"Room audit entry {index} has no usable contour.")
        area = compute_polygon_area(contour)
        perimeter = compute_polygon_perimeter(contour)
        height_value = source.get("height_m")
        height = float(height_value) if height_value is not None else None
        if height is not None and (not math.isfinite(height) or height <= 0):
            raise ValueError(f"Room audit entry {index} has an invalid height.")
        rooms.append(
            {
                "ifc_global_id": source.get("ifc_global_id"),
                "source_name": source.get("source_name"),
                "native_name": source.get("native_name"),
                "native_storey": source.get("native_storey"),
                "source_floor_z_m": source.get("source_floor_z_m"),
                "height_m": height,
                "floor_area_m2": area,
                "perimeter_m": perimeter,
                "wall_area_m2": perimeter * height if height is not None else None,
                "wall_area_method": "room_perimeter_times_height_unadjusted",
                "opening_count": None,
                "opening_area_m2": None,
                "eavg_lux": None,
                "u0": None,
                "ugr": None,
                "luminaire_count": None,
                "volume_m3": area * height if height is not None else None,
                "contour_points": len(contour),
            }
        )
    return {
        "source_file": audit.get("source_file"),
        "native_project": audit.get("native_project"),
        "coordinate_transform": audit.get("coordinate_transform"),
        "storey_count": len(audit.get("verified_storeys", [])),
        "room_count": len(rooms),
        "rooms": rooms,
        "geometry_warnings": audit.get("geometry_warnings", []),
        "parity_status": "GEOMETRY_ONLY",
    }


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _relative_diff(tool: float, reference: float) -> float | None:
    if reference == 0:
        return 0.0 if tool == 0 else None
    return abs(tool - reference) / abs(reference) * 100.0


def compare_room_metrics(
    tool_room: dict[str, Any],
    reference: dict[str, Any],
    tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare one room; only status PASS means the complete workflow is covered."""
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    for key, value in tol.items():
        number = _numeric(value)
        if number is None or number < 0:
            raise ValueError(f"Tolerance '{key}' must be a finite non-negative number.")

    percent_metrics = {
        "floor_area_m2": ("floor_area", "floor_area_pct"),
        "wall_area_m2": ("wall_area", "wall_area_pct"),
        "height_m": ("height", "room_height_pct"),
        "eavg_lux": ("eavg", "eavg_pct"),
        "u0": ("u0", "u0_pct"),
        "opening_area_m2": ("opening_area", "opening_area_pct"),
    }
    results: dict[str, Any] = {
        "room_name": tool_room.get("native_name") or tool_room.get("source_name") or reference.get("room_name"),
        "ifc_global_id": tool_room.get("ifc_global_id") or reference.get("ifc_global_id"),
        "storey": tool_room.get("native_storey") or reference.get("storey"),
        "diffs": {},
        "passed": True,
        "failures": [],
        "missing_metrics": [],
        "invalid_metrics": [],
    }

    all_fields = (*REQUIRED_METRICS, *COMPLETION_METRICS, "ugr")
    for field in all_fields:
        if field == "ugr" and tool_room.get(field) is None and reference.get(field) is None:
            continue
        tool_value = _numeric(tool_room.get(field))
        reference_value = _numeric(reference.get(field))
        if tool_value is None or reference_value is None:
            if field in REQUIRED_METRICS or field in COMPLETION_METRICS or reference.get(field) is not None:
                results["missing_metrics"].append(field)
            continue

        if field in {"opening_count", "luminaire_count"}:
            passed = tool_value == reference_value
            diff = {"tool": tool_value, "ref": reference_value, "tol": "exact", "pass": passed}
            label = field
        elif field == "ugr":
            delta = abs(tool_value - reference_value)
            passed = delta <= tol["ugr_abs"]
            diff = {"tool": tool_value, "ref": reference_value, "delta": delta, "tol": tol["ugr_abs"], "pass": passed}
            label = field
        else:
            label, tolerance_key = percent_metrics[field]
            percentage = _relative_diff(tool_value, reference_value)
            if percentage is None:
                results["invalid_metrics"].append(field)
                continue
            passed = percentage <= tol[tolerance_key]
            diff = {
                "tool": tool_value,
                "ref": reference_value,
                "diff_pct": percentage,
                "tol_pct": tol[tolerance_key],
                "pass": passed,
            }
        results["diffs"][label] = diff
        if not passed:
            results["passed"] = False
            results["failures"].append(f"{field} is outside its recorded tolerance.")

    if results["invalid_metrics"] or (set(results["missing_metrics"]) & set(REQUIRED_METRICS)):
        results["status"] = "INCOMPLETE"
        results["passed"] = False
    elif results["missing_metrics"]:
        results["status"] = "PARTIAL"
    elif not results["passed"]:
        results["status"] = "FAIL"
    else:
        results["status"] = "PASS"
    return results


def _blank_metadata() -> dict[str, Any]:
    return {
        "dialux_version": None,
        "dialux_build": None,
        "license_edition": None,
        "luminaire_article": None,
        "luminaire_file": None,
        "maintenance_factor": None,
        "workplane_height_m": None,
        "workplane_wall_zone_m": None,
        "calculation_grid": None,
        "reflectances": {"ceiling": None, "walls": None, "floor": None},
        "daylight_enabled": None,
    }


def _blank_room_record(room: dict[str, Any]) -> dict[str, Any]:
    return {
        "ifc_global_id": room.get("ifc_global_id"),
        "room_name": room.get("native_name") or room.get("source_name"),
        "storey": room.get("native_storey"),
        **{field: None for field in MEASURED_FIELDS},
        "evidence_path": None,
        "notes": None,
    }


def generate_control_sheet_template(output_path: str | Path) -> None:
    """Write a blank parity record; never seed invented measurements."""
    template = {
        "format": "DIALux IFC Bridge parity record",
        "format_version": 1,
        "kind": "manual_reference",
        "status": "unrecorded",
        "metadata": _blank_metadata(),
        "rooms": [],
        "instructions": (
            "Record values measured in the manual DIALux reference project. Leave unknown fields null. "
            "Do not use example or target values as measured results."
        ),
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(template, file, indent=2, ensure_ascii=False, allow_nan=False)
        file.write("\n")


def generate_measurement_templates(
    audit_path: str | Path,
    output_dir: str | Path,
    room_ids: list[str] | None = None,
) -> tuple[Path, Path]:
    """Create linked manual-reference and generated-project forms from room IDs in an audit."""
    summary = summarize_audit(load_json(audit_path))
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    available = {
        str(room.get("ifc_global_id")): room
        for room in summary["rooms"]
        if room.get("ifc_global_id")
    }
    selected_ids = list(dict.fromkeys(room_ids or available.keys()))
    unknown_ids = sorted(set(selected_ids) - set(available))
    if unknown_ids:
        raise ValueError(f"Requested room GlobalIds are absent from the audit: {unknown_ids}")
    room_records = [_blank_room_record(available[guid]) for guid in selected_ids]
    if not room_records:
        raise ValueError("No rooms were selected for parity measurement templates.")
    common = {
        "format": "DIALux IFC Bridge parity record",
        "format_version": 1,
        "status": "unrecorded",
        "source_ifc": summary.get("source_file"),
        "coordinate_transform": summary.get("coordinate_transform"),
        "metadata": _blank_metadata(),
        "rooms": room_records,
    }
    outputs = (
        (directory / "manual-reference.json", "manual_reference"),
        (directory / "generated-project-results.json", "generated_project_results"),
    )
    for path, kind in outputs:
        document = {
            **common,
            "kind": kind,
            "instructions": (
                "Enter measurements from this actual DIALux run only. Keep GlobalIds unchanged. "
                "Record the same controls in the reference and generated-project files; unknown values stay null."
            ),
        }
        with path.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(document, file, indent=2, ensure_ascii=False, allow_nan=False)
            file.write("\n")
    return outputs[0][0], outputs[1][0]


def _flatten_mapping(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            result.update(_flatten_mapping(item, name))
        else:
            result[name] = item
    return result


def compare_controls(
    reference: dict[str, Any], generated: dict[str, Any]
) -> dict[str, Any]:
    reference_metadata = reference.get("metadata")
    generated_metadata = generated.get("metadata")
    if not isinstance(reference_metadata, dict):
        reference_metadata = {}
    if not isinstance(generated_metadata, dict):
        generated_metadata = {}
    reference_values = _flatten_mapping(reference_metadata)
    generated_values = _flatten_mapping(generated_metadata)
    missing_reference = [
        key for key in REQUIRED_CONTROLS if reference_values.get(key) is None
    ]
    missing_generated = [
        key for key in REQUIRED_CONTROLS if generated_values.get(key) is None
    ]
    mismatches = {
        key: {"reference": reference_values[key], "generated": generated_values[key]}
        for key in REQUIRED_CONTROLS
        if key not in missing_reference
        and key not in missing_generated
        and reference_values[key] != generated_values[key]
    }
    return {
        "status": "INCOMPARABLE" if mismatches else (
            "INCOMPLETE" if missing_reference or missing_generated else "MATCH"
        ),
        "missing_reference_controls": missing_reference,
        "missing_generated_controls": missing_generated,
        "mismatches": mismatches,
    }


def format_markdown_table(comparison_results: list[dict[str, Any]]) -> str:
    lines = [
        "| Room | Storey | Area diff % | Wall diff % | Height diff % | Eavg diff % | Status |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ]
    for result in comparison_results:
        diffs = result.get("diffs", {})
        values = []
        for name in ("floor_area", "wall_area", "height", "eavg"):
            diff = diffs.get(name, {})
            values.append(f"{diff['diff_pct']:.2f}%" if "diff_pct" in diff else "n/a")
        room = str(result.get("room_name") or "Unknown")
        storey = str(result.get("storey") or "Unknown")
        lines.append(
            f"| {room} | {storey} | {values[0]} | {values[1]} | {values[2]} | {values[3]} | "
            f"{result.get('status', 'INCOMPLETE')} |"
        )
    return "\n".join(lines)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Compare manual DIALux measurements with a room audit.")
    parser.add_argument("audit_json", nargs="?", help="Path to *_room_audit.json")
    parser.add_argument("--reference-json", help="Recorded manual reference JSON")
    parser.add_argument("--tool-results-json", help="Measured values from the generated-project DIALux run")
    parser.add_argument("--generate-template", help="Write an empty parity record template")
    parser.add_argument(
        "--generate-templates",
        nargs=2,
        metavar=("AUDIT_JSON", "OUTPUT_DIR"),
        help="Create manual-reference and generated-project measurement forms for audited rooms",
    )
    parser.add_argument(
        "--global-id",
        action="append",
        dest="global_ids",
        help="Limit generated templates to this IFC GlobalId; may be supplied more than once",
    )
    parser.add_argument("--markdown", action="store_true", help="Print a Markdown results table")
    args = parser.parse_args()

    try:
        if args.generate_templates:
            reference_path, results_path = generate_measurement_templates(
                *args.generate_templates, room_ids=args.global_ids
            )
            print(f"Manual reference template: {reference_path}")
            print(f"Generated project results template: {results_path}")
            return 0
        if args.generate_template:
            generate_control_sheet_template(args.generate_template)
            print(f"Blank parity record written to {args.generate_template}")
            return 0
        if not args.audit_json or not args.reference_json:
            parser.error(
                "provide AUDIT_JSON and --reference-json, or use --generate-template/--generate-templates"
            )

        summary = summarize_audit(load_json(args.audit_json))
        reference_document = load_json(args.reference_json)
        generated_document = (
            load_json(args.tool_results_json) if args.tool_results_json else {"rooms": []}
        )
        controls = compare_controls(reference_document, generated_document)
        reference_rooms = reference_document.get("rooms")
        if not isinstance(reference_rooms, list) or not reference_rooms:
            raise ValueError("Reference JSON has no recorded room measurements.")
        tool_by_id: dict[str, dict[str, Any]] = {}
        for room in summary["rooms"]:
            guid = str(room.get("ifc_global_id") or "")
            if not guid:
                continue
            if guid in tool_by_id:
                raise ValueError(f"Room audit contains duplicate IFC GlobalId '{guid}'.")
            tool_by_id[guid] = room
        reference_by_id: dict[str, dict[str, Any]] = {}
        for room in reference_rooms:
            if not isinstance(room, dict) or not room.get("ifc_global_id"):
                raise ValueError("Every reference room must include its IFC GlobalId.")
            guid = str(room["ifc_global_id"])
            if guid in reference_by_id:
                raise ValueError(f"Reference JSON contains duplicate IFC GlobalId '{guid}'.")
            reference_by_id[guid] = room
        generated_rooms = generated_document.get("rooms")
        if not isinstance(generated_rooms, list):
            raise ValueError("Generated-project results JSON must contain a 'rooms' array.")
        generated_by_id: dict[str, dict[str, Any]] = {}
        for room in generated_rooms:
            if not isinstance(room, dict) or not room.get("ifc_global_id"):
                raise ValueError("Every generated-project result must include its IFC GlobalId.")
            guid = str(room["ifc_global_id"])
            if guid in generated_by_id:
                raise ValueError(f"Generated-project results contain duplicate IFC GlobalId '{guid}'.")
            generated_by_id[guid] = room

        comparisons = []
        unmatched_reference_ids = []
        for guid, reference in reference_by_id.items():
            audit_room = tool_by_id.get(guid)
            if audit_room is None:
                unmatched_reference_ids.append(guid)
                continue
            generated_room = generated_by_id.get(guid, {})
            measured_room = {
                **audit_room,
                **{field: generated_room.get(field) for field in MEASURED_FIELDS},
            }
            comparisons.append(compare_room_metrics(measured_room, reference))

        status = "PASS"
        if controls["status"] == "INCOMPARABLE":
            status = "INCOMPARABLE"
        elif controls["status"] == "INCOMPLETE" or not comparisons or unmatched_reference_ids or any(
            item["status"] in {"PARTIAL", "INCOMPLETE"} for item in comparisons
        ):
            status = "INCOMPLETE"
        elif any(not item["passed"] for item in comparisons):
            status = "FAIL"
        report = {
            "status": status,
            "controls": controls,
            "matched_room_count": len(comparisons),
            "tool_room_count": summary["room_count"],
            "reference_room_count": len(reference_rooms),
            "unreferenced_tool_room_count": summary["room_count"] - len(comparisons),
            "unmatched_reference_global_ids": sorted(unmatched_reference_ids),
            "comparisons": comparisons,
        }
        if args.markdown:
            print(format_markdown_table(comparisons))
            print(f"\nOverall status: {status}")
            print(f"Control sheet: {controls['status']}")
            if unmatched_reference_ids:
                print(f"Reference GlobalIds missing from room audit: {len(unmatched_reference_ids)}")
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
        if status == "PASS":
            return 0
        return 1 if status == "FAIL" else 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Parity comparison could not be completed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
