"""Unit tests for lighting parity audit and comparison tool."""

from __future__ import annotations

import unittest
from tools.lighting_parity_compare import (
    DEFAULT_TOLERANCES,
    compare_room_metrics,
    compute_polygon_area,
    compute_polygon_perimeter,
    summarize_audit,
)


class LightingParityTests(unittest.TestCase):
    def test_shoelace_area_and_perimeter(self) -> None:
        # 10m x 5m rectangle: area = 50, perimeter = 30
        rect = [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]]
        self.assertAlmostEqual(compute_polygon_area(rect), 50.0, places=4)
        self.assertAlmostEqual(compute_polygon_perimeter(rect), 30.0, places=4)

        # Right triangle with legs 3 and 4: area = 6, perimeter = 12
        tri = [[0.0, 0.0], [3.0, 0.0], [0.0, 4.0]]
        self.assertAlmostEqual(compute_polygon_area(tri), 6.0, places=4)
        self.assertAlmostEqual(compute_polygon_perimeter(tri), 12.0, places=4)

        # Degenerate cases
        self.assertEqual(compute_polygon_area([]), 0.0)
        self.assertEqual(compute_polygon_perimeter([]), 0.0)
        self.assertEqual(compute_polygon_area([[1.0, 1.0]]), 0.0)
        self.assertEqual(compute_polygon_perimeter([[1.0, 1.0]]), 0.0)

    def test_summarize_audit_computes_metrics(self) -> None:
        raw_audit = {
            "source_file": "sample.ifc",
            "native_project": "sample.evo",
            "verified_storeys": [{"name": "Ground Floor", "elevation_m": 0.0}],
            "rooms": [
                {
                    "ifc_global_id": "GUID1",
                    "source_name": "Classroom 101",
                    "native_name": "Classroom 101",
                    "native_storey": "Ground Floor",
                    "source_floor_z_m": 0.0,
                    "height_m": 3.0,
                    "native_contour_xy_m": [[0.0, 0.0], [6.0, 0.0], [6.0, 8.0], [0.0, 8.0]],
                }
            ],
            "geometry_warnings": [],
        }
        summary = summarize_audit(raw_audit)
        self.assertEqual(summary["room_count"], 1)
        room = summary["rooms"][0]
        self.assertAlmostEqual(room["floor_area_m2"], 48.0, places=4)
        self.assertAlmostEqual(room["perimeter_m"], 28.0, places=4)
        self.assertAlmostEqual(room["wall_area_m2"], 84.0, places=4)
        self.assertAlmostEqual(room["volume_m3"], 144.0, places=4)

    def test_compare_room_metrics_tolerances(self) -> None:
        tool_room = {
            "native_name": "Office 102",
            "ifc_global_id": "GUID2",
            "native_storey": "Ground Floor",
            "floor_area_m2": 50.2,  # 0.4% diff from 50.0 (passes 1% tol)
            "wall_area_m2": 30.5,   # 1.6% diff from 30.0 (passes 3% tol)
            "height_m": 3.01,       # 0.33% diff from 3.0 (passes 1% tol)
            "eavg_lux": 510.0,      # 2.0% diff from 500.0 (passes 3% tol)
            "u0": 0.62,             # 3.3% diff from 0.60 (passes 5% tol)
            "ugr": 18.5,            # 0.5 delta from 19.0 (passes 1.0 tol)
        }
        reference = {
            "floor_area_m2": 50.0,
            "wall_area_m2": 30.0,
            "height_m": 3.0,
            "eavg_lux": 500.0,
            "u0": 0.60,
            "ugr": 19.0,
        }
        result = compare_room_metrics(tool_room, reference)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["failures"]), 0)

        # Now test exceeding tolerance
        failing_room = dict(tool_room)
        failing_room["floor_area_m2"] = 55.0  # 10% diff (exceeds 1% tol)
        failing_result = compare_room_metrics(failing_room, reference)
        self.assertFalse(failing_result["passed"])
        self.assertEqual(len(failing_result["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
