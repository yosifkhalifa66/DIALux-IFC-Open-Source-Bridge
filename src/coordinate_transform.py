"""Shared IFC-world to DIALux/export coordinate conversion."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoordinateTransform:
    source_unit_to_meters: float = 1.0
    origin_offset_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    output_units_per_meter: float = 1.0
    scale_factor: float = 1.0
    rotation_radians: float = 0.0
    origin_basis: str = "explicit"

    def __post_init__(self) -> None:
        if not math.isfinite(self.source_unit_to_meters) or self.source_unit_to_meters <= 0:
            raise ValueError("The source-unit scale must be a positive finite number.")
        if len(self.origin_offset_m) != 3 or not all(
            math.isfinite(value) for value in self.origin_offset_m
        ):
            raise ValueError("The coordinate origin must contain three finite meter values.")
        if not math.isfinite(self.output_units_per_meter) or self.output_units_per_meter <= 0:
            raise ValueError("The output-unit scale must be a positive finite number.")
        if not math.isfinite(self.scale_factor) or self.scale_factor <= 0:
            raise ValueError("The additional scale factor must be a positive finite number.")
        if not math.isfinite(self.rotation_radians):
            raise ValueError("The coordinate rotation must be finite.")
        if not self.origin_basis.strip():
            raise ValueError("The coordinate origin basis must not be empty.")

    @classmethod
    def centered_on_room_contours(
        cls,
        room_contours_m: Iterable[Iterable[Sequence[float]]],
        *,
        source_unit_to_meters: float,
        output_units_per_meter: float,
        scale_factor: float = 1.0,
        rotation_radians: float = 0.0,
    ) -> CoordinateTransform:
        points = [point for contour in room_contours_m for point in contour]
        if not points:
            raise ValueError("Cannot choose a room-centered origin without room contour points.")
        if any(len(point) != 2 or not all(math.isfinite(value) for value in point) for point in points):
            raise ValueError("Room contours must contain finite XY points in meters.")
        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)
        return cls(
            source_unit_to_meters=source_unit_to_meters,
            origin_offset_m=((min_x + max_x) / 2, (min_y + max_y) / 2, 0.0),
            output_units_per_meter=output_units_per_meter,
            scale_factor=scale_factor,
            rotation_radians=rotation_radians,
            origin_basis="selected_room_bounds_center",
        )

    @property
    def effective_output_scale(self) -> float:
        return self.source_unit_to_meters * self.output_units_per_meter * self.scale_factor

    def require_compatible_export(
        self,
        *,
        source_unit_to_meters: float,
        output_units_per_meter: float,
        scale_factor: float,
    ) -> None:
        if (
            not math.isclose(self.source_unit_to_meters, source_unit_to_meters, rel_tol=1e-12)
            or not math.isclose(self.output_units_per_meter, output_units_per_meter, rel_tol=1e-12)
            or not math.isclose(self.scale_factor, scale_factor, rel_tol=1e-12)
        ):
            raise ValueError("The shared coordinate transform does not match the export unit settings.")

    def to_project_xy(self, point_m: tuple[float, float]) -> tuple[float, float]:
        if len(point_m) != 2 or not all(math.isfinite(value) for value in point_m):
            raise ValueError("A project XY point must contain two finite meter coordinates.")
        x = point_m[0] - self.origin_offset_m[0]
        y = point_m[1] - self.origin_offset_m[1]
        cosine = math.cos(self.rotation_radians)
        sine = math.sin(self.rotation_radians)
        transformed = (cosine * x - sine * y, sine * x + cosine * y)
        if not all(math.isfinite(value) for value in transformed):
            raise ValueError("The transformed project coordinates exceed the supported numeric range.")
        return transformed

    def to_project_point_m(self, point_m: tuple[float, float, float]) -> tuple[float, float, float]:
        if len(point_m) != 3 or not all(math.isfinite(value) for value in point_m):
            raise ValueError("A project point must contain three finite meter coordinates.")
        x, y = self.to_project_xy((point_m[0], point_m[1]))
        return x, y, point_m[2] - self.origin_offset_m[2]

    def to_project_elevation(self, elevation_m: float) -> float:
        if not math.isfinite(elevation_m):
            raise ValueError("A project elevation must be finite.")
        return elevation_m - self.origin_offset_m[2]

    def to_output_point(self, point_source_units: tuple[float, float, float]) -> tuple[float, float, float]:
        if len(point_source_units) != 3 or not all(
            math.isfinite(value) for value in point_source_units
        ):
            raise ValueError("An output point must contain three finite source coordinates.")
        point_m = tuple(value * self.source_unit_to_meters for value in point_source_units)
        point_project_m = self.to_project_point_m(point_m)
        output_scale = self.output_units_per_meter * self.scale_factor
        output = tuple(value * output_scale for value in point_project_m)
        if not all(math.isfinite(value) for value in output):
            raise ValueError("The transformed output coordinates exceed the supported numeric range.")
        return output

    def to_metadata(self) -> dict[str, float | str | list[float]]:
        return {
            "source_unit_to_meters": self.source_unit_to_meters,
            "origin_offset_m": list(self.origin_offset_m),
            "output_units_per_meter": self.output_units_per_meter,
            "scale_factor": self.scale_factor,
            "rotation_radians": self.rotation_radians,
            "origin_basis": self.origin_basis,
        }
