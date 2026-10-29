from __future__ import annotations

import csv
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import threading

import ifcopenshell

from src.architecture_inventory import IfcArchitectureInventoryExporter
from src.coordinate_transform import CoordinateTransform
from src.dialux_bridge import find_dialux_executable, send_to_dialux
from src.dxf_exporter import DialuxDxfExporter
from src.ifc_parser import IfcModelInspector
from src.native_exporter import (
    DialuxNativeProjectExporter,
    _compound_angle_to_degrees,
    build_native_model_plan,
)
from src.obj_exporter import DialuxObjExporter
from src.stf_exporter import DialuxStfExporter


def create_minimal_ifc(path: str, include_storey: bool = True) -> None:
    model = ifcopenshell.file(schema="IFC4")
    millimetre = model.create_entity(
        "IfcSIUnit",
        UnitType="LENGTHUNIT",
        Prefix="MILLI",
        Name="METRE",
    )
    units = model.create_entity("IfcUnitAssignment", Units=[millimetre])
    model.create_entity(
        "IfcProject",
        GlobalId="0000000000000000000001",
        Name="Scaling Test",
        UnitsInContext=units,
    )
    storey = None
    if include_storey:
        storey = model.create_entity(
            "IfcBuildingStorey",
            GlobalId="0000000000000000000002",
            Name="Level 1",
            Elevation=3000.0,
        )
    wall = model.create_entity(
        "IfcWall",
        GlobalId="0000000000000000000003",
        Name="Test wall",
    )
    space = model.create_entity(
        "IfcSpace",
        GlobalId="0000000000000000000004",
        Name="Room 101",
        LongName="Meeting room",
        CompositionType="ELEMENT",
    )
    model.create_entity(
        "IfcZone",
        GlobalId="0000000000000000000007",
        Name="Lighting zone",
    )
    if storey is not None:
        model.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId="0000000000000000000005",
            RelatedElements=[space],
            RelatingStructure=storey,
        )
        model.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId="0000000000000000000008",
            RelatedElements=[wall],
            RelatingStructure=space,
        )
    model.create_entity(
        "IfcRelSpaceBoundary",
        GlobalId="0000000000000000000006",
        RelatingSpace=space,
        RelatedBuildingElement=wall,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="INTERNAL",
    )
    model.write(path)


def create_mm_geometry_ifc(path: str) -> None:
    model = ifcopenshell.file(schema="IFC4")
    length_unit = model.create_entity(
        "IfcSIUnit",
        UnitType="LENGTHUNIT",
        Prefix="MILLI",
        Name="METRE",
    )
    units = model.create_entity("IfcUnitAssignment", Units=[length_unit])
    origin = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    z_axis = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    x_axis = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    axis = model.create_entity("IfcAxis2Placement3D", Location=origin, Axis=z_axis, RefDirection=x_axis)
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier=None,
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=axis,
        TrueNorth=None,
    )
    body_context = model.create_entity(
        "IfcGeometricRepresentationSubContext",
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=context,
        TargetScale=None,
        TargetView="MODEL_VIEW",
        UserDefinedTargetView=None,
    )
    model.create_entity(
        "IfcProject",
        GlobalId="0000000000000000000001",
        Name="Millimetre geometry",
        RepresentationContexts=[context],
        UnitsInContext=units,
    )
    points = model.create_entity(
        "IfcCartesianPointList2D",
        CoordList=((0.0, 0.0), (0.0, 200.0), (6000.0, 200.0), (6000.0, 0.0), (0.0, 0.0)),
    )
    curve = model.create_entity("IfcIndexedPolyCurve", Points=points, Segments=None, SelfIntersect=False)
    profile = model.create_entity(
        "IfcArbitraryClosedProfileDef",
        ProfileType="AREA",
        ProfileName=None,
        OuterCurve=curve,
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axis,
        ExtrudedDirection=z_axis,
        Depth=3000.0,
    )
    representation = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    product_shape = model.create_entity(
        "IfcProductDefinitionShape",
        Name=None,
        Description=None,
        Representations=[representation],
    )
    placement = model.create_entity("IfcLocalPlacement", PlacementRelTo=None, RelativePlacement=axis)
    model.create_entity(
        "IfcWall",
        GlobalId="0000000000000000000002",
        Name="Six metre wall",
        ObjectPlacement=placement,
        Representation=product_shape,
    )
    model.write(path)


def create_geometry_ifc(
    path: str,
    unit: str,
    prefix: str | None,
    dimensions: tuple[float, float, float],
    ifc_class: str = "IfcWall",
) -> None:
    model = ifcopenshell.file(schema="IFC4")
    if unit == "FOOT":
        metre = model.create_entity(
            "IfcSIUnit",
            UnitType="LENGTHUNIT",
            Prefix=None,
            Name="METRE",
        )
        ratio = model.create_entity(
            "IfcMeasureWithUnit",
            ValueComponent=model.create_entity("IfcReal", 0.3048),
            UnitComponent=metre,
        )
        length_unit = model.create_entity(
            "IfcConversionBasedUnit",
            Dimensions=None,
            UnitType="LENGTHUNIT",
            Name="FOOT",
            ConversionFactor=ratio,
        )
    else:
        length_unit = model.create_entity(
            "IfcSIUnit",
            UnitType="LENGTHUNIT",
            Prefix=prefix,
            Name=unit,
        )
    units = model.create_entity("IfcUnitAssignment", Units=[length_unit])
    origin = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    z_axis = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    x_axis = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    axis = model.create_entity("IfcAxis2Placement3D", Location=origin, Axis=z_axis, RefDirection=x_axis)
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier=None,
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=axis,
        TrueNorth=None,
    )
    body_context = model.create_entity(
        "IfcGeometricRepresentationSubContext",
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=context,
        TargetScale=None,
        TargetView="MODEL_VIEW",
        UserDefinedTargetView=None,
    )
    model.create_entity(
        "IfcProject",
        GlobalId="0000000000000000000001",
        Name="Unit geometry",
        RepresentationContexts=[context],
        UnitsInContext=units,
    )
    length, thickness, height = dimensions
    points = model.create_entity(
        "IfcCartesianPointList2D",
        CoordList=(
            (0.0, 0.0),
            (0.0, thickness),
            (length, thickness),
            (length, 0.0),
            (0.0, 0.0),
        ),
    )
    curve = model.create_entity("IfcIndexedPolyCurve", Points=points, Segments=None, SelfIntersect=False)
    profile = model.create_entity(
        "IfcArbitraryClosedProfileDef",
        ProfileType="AREA",
        ProfileName=None,
        OuterCurve=curve,
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axis,
        ExtrudedDirection=z_axis,
        Depth=height,
    )
    representation = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    product_shape = model.create_entity(
        "IfcProductDefinitionShape",
        Name=None,
        Description=None,
        Representations=[representation],
    )
    placement = model.create_entity("IfcLocalPlacement", PlacementRelTo=None, RelativePlacement=axis)
    if ifc_class == "IfcSpace":
        room = model.create_entity(
            "IfcSpace",
            GlobalId="0000000000000000000002",
            Name="Meeting room",
            LongName="Meeting room",
            CompositionType="ELEMENT",
            PredefinedType="INTERNAL",
            ObjectPlacement=placement,
            Representation=product_shape,
        )
        storey = model.create_entity(
            "IfcBuildingStorey",
            GlobalId="0000000000000000000003",
            Name="Ground Floor",
            Elevation=0.0,
        )
        model.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId="0000000000000000000004",
            RelatedElements=[room],
            RelatingStructure=storey,
        )
    else:
        model.create_entity(
            ifc_class,
            GlobalId="0000000000000000000002",
            Name="Test dimension wall",
            ObjectPlacement=placement,
            Representation=product_shape,
        )
    model.write(path)


class IfcParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ifc_path = os.path.join(self.temp_dir.name, "minimal_mm.ifc")
        create_minimal_ifc(self.ifc_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reads_units_storeys_spaces_and_boundaries(self) -> None:
        inspector = IfcModelInspector(self.ifc_path).load()
        summary = inspector.get_summary()
        self.assertEqual(summary["schema"], "IFC4")
        self.assertEqual(summary["detected_unit"], "MILLIMETRE")
        self.assertAlmostEqual(summary["unit_scale_to_meters"], 0.001)
        self.assertEqual(summary["storeys"][0]["name"], "Level 1")
        self.assertAlmostEqual(summary["storeys"][0]["elevation"], 3.0)
        self.assertEqual(summary["category_counts"]["IfcWall"], 1)
        self.assertEqual(summary["category_counts"]["IfcSpace"], 1)
        self.assertEqual(summary["category_counts"]["IfcZone"], 1)
        self.assertEqual(inspector.element_to_storey["0000000000000000000003"], "Level 1")
        self.assertEqual(summary["rooms"][0]["name"], "Room 101")
        self.assertEqual(summary["rooms"][0]["storey"], "Level 1")
        self.assertEqual(summary["space_boundaries_count"], 1)

    def test_maps_spaces_aggregated_under_storeys(self) -> None:
        path = os.path.join(self.temp_dir.name, "aggregated_space.ifc")
        create_minimal_ifc(path)
        model = ifcopenshell.open(path)
        space = model.by_type("IfcSpace")[0]
        storey = model.by_type("IfcBuildingStorey")[0]
        for relation in model.by_type("IfcRelContainedInSpatialStructure"):
            if space in (relation.RelatedElements or ()):
                model.remove(relation)
        model.create_entity(
            "IfcRelAggregates",
            GlobalId="0000000000000000000009",
            RelatingObject=storey,
            RelatedObjects=[space],
        )
        model.write(path)

        inspector = IfcModelInspector(path).load()
        self.assertEqual(inspector.rooms[0]["storey"], "Level 1")
        self.assertEqual(inspector.element_to_storey["0000000000000000000004"], "Level 1")

    def test_marks_missing_storey_elevation_for_geometry_fallback(self) -> None:
        inspector = IfcModelInspector(self.ifc_path).load()
        inspector.ifc_file.by_type("IfcBuildingStorey")[0].Elevation = None
        inspector._index_spatial_structure()
        storey = next(item for item in inspector.storeys if item["name"] == "Level 1")
        self.assertFalse(storey["elevation_defined"])
        self.assertIsNone(DialuxStfExporter(inspector)._storey_elevation("Level 1"))

    def test_reports_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            IfcModelInspector(os.path.join(self.temp_dir.name, "missing.ifc")).load()

    def test_assigns_uncontained_elements_when_storey_is_missing(self) -> None:
        path = os.path.join(self.temp_dir.name, "no_storey.ifc")
        create_minimal_ifc(path, include_storey=False)
        inspector = IfcModelInspector(path).load()
        self.assertEqual(inspector.storeys[0]["name"], "All Levels")
        self.assertEqual(set(inspector.element_to_storey.values()), {"All Levels"})
        self.assertEqual(inspector.rooms[0]["storey"], "All Levels")


class ArchitectureInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ifc_path = os.path.join(self.temp_dir.name, "architecture.ifc")
        create_minimal_ifc(self.ifc_path)
        model = ifcopenshell.open(self.ifc_path)
        wall = model.by_type("IfcWall")[0]
        opening = model.create_entity(
            "IfcOpeningElement",
            GlobalId="0000000000000000000009",
            Name="Door opening",
        )
        door = model.create_entity(
            "IfcDoor",
            GlobalId="0000000000000000000010",
            Name="Door 101",
        )
        model.create_entity(
            "IfcRelVoidsElement",
            GlobalId="0000000000000000000011",
            RelatingBuildingElement=wall,
            RelatedOpeningElement=opening,
        )
        model.create_entity(
            "IfcRelFillsElement",
            GlobalId="0000000000000000000012",
            RelatingOpeningElement=opening,
            RelatedBuildingElement=door,
        )
        model.write(self.ifc_path)
        self.inspector = IfcModelInspector(self.ifc_path).load()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_exports_exact_opening_host_and_filling_relations(self) -> None:
        output_path = os.path.join(self.temp_dir.name, "architecture.json")
        transform = CoordinateTransform(
            source_unit_to_meters=self.inspector.unit_scale_to_meters,
            origin_offset_m=(1.0, 2.0, 0.0),
        )
        result = IfcArchitectureInventoryExporter(self.inspector).export(
            output_path,
            coordinate_transform=transform,
        )
        inventory = json.loads(Path(output_path).read_text(encoding="utf-8"))
        relation = inventory["relationships"][0]
        self.assertEqual(relation["opening"]["global_id"], "0000000000000000000009")
        self.assertEqual(relation["hosts"][0]["global_id"], "0000000000000000000003")
        self.assertEqual(relation["fillings"][0]["global_id"], "0000000000000000000010")
        self.assertEqual(inventory["summary"]["opening_count"], 1)
        self.assertEqual(inventory["summary"]["opening_count_with_hosts"], 1)
        self.assertEqual(inventory["summary"]["opening_count_with_fillings"], 1)
        self.assertEqual(result["element_count"], 3)
        self.assertEqual(inventory["coordinate_transform"]["origin_offset_m"], [1.0, 2.0, 0.0])

    def test_refuses_to_overwrite_an_existing_inventory(self) -> None:
        output_path = os.path.join(self.temp_dir.name, "architecture.json")
        Path(output_path).write_text("preserve", encoding="utf-8")
        transform = CoordinateTransform(
            source_unit_to_meters=self.inspector.unit_scale_to_meters,
        )
        with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
            IfcArchitectureInventoryExporter(self.inspector).export(
                output_path,
                coordinate_transform=transform,
            )

    def test_geometry_bounds_follow_shared_project_transform(self) -> None:
        geometry_path = os.path.join(self.temp_dir.name, "wall_geometry.ifc")
        create_geometry_ifc(geometry_path, "METRE", None, (6.0, 0.2, 3.0))
        inspector = IfcModelInspector(geometry_path).load()
        transform = CoordinateTransform(
            source_unit_to_meters=inspector.unit_scale_to_meters,
            origin_offset_m=(1.0, 2.0, 0.0),
        )
        output_path = os.path.join(self.temp_dir.name, "wall_inventory.json")
        IfcArchitectureInventoryExporter(inspector).export(
            output_path,
            coordinate_transform=transform,
        )
        inventory = json.loads(Path(output_path).read_text(encoding="utf-8"))
        wall = next(element for element in inventory["elements"] if element["ifc_type"] == "IfcWall")
        bounds = wall["geometry_bounds"]
        self.assertAlmostEqual(bounds["world_min_m"][0], 0.0)
        self.assertAlmostEqual(bounds["world_max_m"][0], 6.0)
        self.assertAlmostEqual(bounds["project_min_m"][0], -1.0)
        self.assertAlmostEqual(bounds["project_min_m"][1], -2.0)
        self.assertAlmostEqual(bounds["project_max_m"][0], 5.0)
        self.assertAlmostEqual(bounds["project_max_m"][1], -1.8)

    def test_inventory_extracts_geometry_for_native_tier_elements(self) -> None:
        for ifc_class in ("IfcColumn", "IfcFurnishingElement"):
            with self.subTest(ifc_class=ifc_class):
                geometry_path = os.path.join(self.temp_dir.name, f"{ifc_class}.ifc")
                create_geometry_ifc(
                    geometry_path,
                    "METRE",
                    None,
                    (0.4, 0.3, 3.0),
                    ifc_class=ifc_class,
                )
                inspector = IfcModelInspector(geometry_path).load()
                output_path = os.path.join(self.temp_dir.name, f"{ifc_class}_inventory.json")
                IfcArchitectureInventoryExporter(inspector).export(
                    output_path,
                    coordinate_transform=CoordinateTransform(
                        source_unit_to_meters=inspector.unit_scale_to_meters,
                        origin_offset_m=(1.0, 2.0, 0.0),
                    ),
                )
                inventory = json.loads(Path(output_path).read_text(encoding="utf-8"))
                element = next(
                    item
                    for item in inventory["elements"]
                    if item["ifc_type"] == ifc_class
                )
                self.assertIsNotNone(element["geometry_bounds"])
                self.assertAlmostEqual(element["geometry_bounds"]["world_max_m"][2], 3.0)
                self.assertEqual(element["geometry_bounds"]["vertex_count"], 8)

    def test_inventory_preserves_curtain_wall_assembly_components(self) -> None:
        model = ifcopenshell.open(self.ifc_path)
        curtain_wall = model.create_entity(
            "IfcCurtainWall",
            GlobalId="0000000000000000000013",
            Name="Curtain system",
        )
        panel = model.create_entity(
            "IfcPlate",
            GlobalId="0000000000000000000014",
            Name="Glazed panel",
        )
        mullion = model.create_entity(
            "IfcMember",
            GlobalId="0000000000000000000015",
            Name="Mullion",
        )
        model.create_entity(
            "IfcRelAggregates",
            GlobalId="0000000000000000000016",
            RelatingObject=curtain_wall,
            RelatedObjects=[panel, mullion],
        )
        model.write(self.ifc_path)
        inspector = IfcModelInspector(self.ifc_path).load()
        output_path = os.path.join(self.temp_dir.name, "assembly_inventory.json")
        transform = CoordinateTransform(
            source_unit_to_meters=inspector.unit_scale_to_meters,
        )
        IfcArchitectureInventoryExporter(inspector).export(
            output_path,
            coordinate_transform=transform,
        )
        inventory = json.loads(Path(output_path).read_text(encoding="utf-8"))
        assembly = next(
            item
            for item in inventory["assemblies"]
            if item["parent"]["global_id"] == "0000000000000000000013"
        )
        self.assertEqual(
            {component["ifc_type"] for component in assembly["components"]},
            {"IfcMember", "IfcPlate"},
        )
        self.assertEqual(inventory["summary"]["curtain_wall_assembly_count"], 1)
        self.assertEqual(
            inventory["summary"]["curtain_wall_component_counts_by_ifc_type"],
            {"IfcMember": 1, "IfcPlate": 1},
        )


class CoordinateTransformTests(unittest.TestCase):
    def test_room_bounds_center_is_a_valid_shared_origin(self) -> None:
        transform = CoordinateTransform.centered_on_room_contours(
            [
                [(10.0, -5.0), (12.0, -5.0), (12.0, -1.0), (10.0, -1.0)],
                [(14.0, -2.0), (16.0, -2.0), (16.0, 0.0)],
            ],
            source_unit_to_meters=0.001,
            output_units_per_meter=1000.0,
        )
        self.assertEqual(transform.origin_offset_m, (13.0, -2.5, 0.0))
        self.assertEqual(transform.origin_basis, "selected_room_bounds_center")
        self.assertEqual(transform.to_project_xy((13.0, -2.5)), (0.0, 0.0))

    def test_room_bounds_center_rejects_empty_or_invalid_contours(self) -> None:
        with self.assertRaisesRegex(ValueError, "without room contour points"):
            CoordinateTransform.centered_on_room_contours(
                [],
                source_unit_to_meters=1.0,
                output_units_per_meter=1.0,
            )
        with self.assertRaisesRegex(ValueError, "finite XY points"):
            CoordinateTransform.centered_on_room_contours(
                [[(0.0, math.nan)]],
                source_unit_to_meters=1.0,
                output_units_per_meter=1.0,
            )

    def test_scales_rotates_rebases_and_transforms_storey_elevation(self) -> None:
        transform = CoordinateTransform(
            source_unit_to_meters=0.001,
            origin_offset_m=(1.0, 2.0, 3.0),
            output_units_per_meter=1000.0,
            rotation_radians=math.pi / 2,
        )
        for actual, expected in zip(
            transform.to_output_point((2000.0, 2000.0, 6000.0)),
            (0.0, 1000.0, 3000.0),
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(transform.to_project_elevation(3.0), 0.0)


class ObjGeometryExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ifc_path = os.path.join(self.temp_dir.name, "minimal_mm.ifc")
        create_minimal_ifc(self.ifc_path)
        self.inspector = IfcModelInspector(self.ifc_path).load()
        self.output_path = os.path.join(self.temp_dir.name, "model.obj")
        self.shape = SimpleNamespace(
            geometry=SimpleNamespace(
                verts=(1000.0, 2000.0, 3000.0, 2000.0, 2000.0, 3000.0, 1000.0, 3000.0, 3000.0),
                faces=(0, 1, 2),
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_real_millimetre_geometry_exports_at_six_metres(self) -> None:
        path = os.path.join(self.temp_dir.name, "geometry_mm.ifc")
        create_mm_geometry_ifc(path)
        inspector = IfcModelInspector(path).load()
        output = os.path.join(self.temp_dir.name, "geometry.obj")
        result = DialuxObjExporter(inspector).export(output, selected_categories=["IfcWall"])
        vertices = []
        with open(result["obj_path"], encoding="utf-8") as model_file:
            for line in model_file:
                if line.startswith("v "):
                    vertices.append(tuple(float(value) for value in line.split()[1:]))
        spans = [
            max(vertex[axis] for vertex in vertices) - min(vertex[axis] for vertex in vertices)
            for axis in range(3)
        ]
        self.assertEqual(inspector.unit_scale_to_meters, 0.001)
        self.assertAlmostEqual(max(spans), 6.0, places=5)
        self.assertAlmostEqual(min(spans), 0.2, places=5)
        self.assertAlmostEqual(sorted(spans)[1], 3.0, places=5)

    def test_real_foot_geometry_exports_at_expected_metres(self) -> None:
        path = os.path.join(self.temp_dir.name, "geometry_ft.ifc")
        create_geometry_ifc(path, "FOOT", None, (10.0, 0.5, 8.0))
        inspector = IfcModelInspector(path).load()
        output = os.path.join(self.temp_dir.name, "geometry_ft.obj")
        result = DialuxObjExporter(inspector).export(output, selected_categories=["IfcWall"])
        with open(result["obj_path"], encoding="utf-8") as model_file:
            vertices = [
                tuple(float(value) for value in line.split()[1:])
                for line in model_file
                if line.startswith("v ")
            ]
        spans = [
            max(vertex[axis] for vertex in vertices) - min(vertex[axis] for vertex in vertices)
            for axis in range(3)
        ]
        expected = (3.048, 0.1524, 2.4384)
        for actual, target in zip(sorted(spans), sorted(expected)):
            self.assertAlmostEqual(actual, target, places=5)

    def test_reads_real_ifc_surface_style_color(self) -> None:
        path = os.path.join(self.temp_dir.name, "styled_geometry.ifc")
        create_geometry_ifc(path, "METRE", None, (6.0, 0.5, 3.0))
        model = ifcopenshell.open(path)
        surface_color = model.createIfcColourRgb(None, 0.12, 0.30, 0.50)
        rendering = model.createIfcSurfaceStyleRendering(
            surface_color, 0.0, None, None, None, None, None, None, "NOTDEFINED"
        )
        style = model.createIfcSurfaceStyle("IFC finish", "BOTH", [rendering])
        model.createIfcStyledItem(model.by_type("IfcExtrudedAreaSolid")[0], [style], None)
        model.write(path)

        inspector = IfcModelInspector(path).load()
        result = DialuxObjExporter(inspector).export(
            os.path.join(self.temp_dir.name, "styled.obj"),
            selected_categories=["IfcWall"],
        )
        mtl_text = Path(result["mtl_path"]).read_text(encoding="utf-8")
        self.assertIn("Kd 0.1200 0.3000 0.5000", mtl_text)

    def test_shared_transform_aligns_obj_dxf_and_native_room_coordinates(self) -> None:
        room = {
            "name": "Room",
            "source_storey": "Level 1",
            "source_storey_elevation_m": 3.0,
            "floor_z_m": 3.0,
            "height_m": 3.0,
            "contour_m": [(1.0, 2.0), (2.0, 2.0), (2.0, 3.0)],
        }
        transform = CoordinateTransform.centered_on_room_contours(
            [room["contour_m"]],
            source_unit_to_meters=self.inspector.unit_scale_to_meters,
            output_units_per_meter=1.0,
        )
        with (
            mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape", return_value=self.shape),
            mock.patch("src.dxf_exporter.ifcopenshell.geom.create_shape", return_value=self.shape),
        ):
            obj = DialuxObjExporter(self.inspector).export(
                self.output_path,
                selected_categories=["IfcWall"],
                selected_storeys=["Level 1"],
                coordinate_transform=transform,
            )
            plan = build_native_model_plan(
                self.inspector,
                [room],
                coordinate_transform=transform,
            )
            dxf = DialuxDxfExporter(self.inspector).export(
                os.path.join(self.temp_dir.name, "model.dxf"),
                selected_categories=["IfcWall"],
                selected_storeys=["Level 1"],
                coordinate_transform=transform,
            )

        obj_vertices = [
            line.split()[1:]
            for line in Path(obj["obj_path"]).read_text(encoding="utf-8").splitlines()
            if line.startswith("v ")
        ]
        dxf_lines = Path(dxf["dxf_path"]).read_text(encoding="ascii").splitlines()
        face_start = next(
            index
            for index in range(len(dxf_lines) - 1)
            if dxf_lines[index] == "0" and dxf_lines[index + 1] == "3DFACE"
        )
        face_coordinates = {}
        for index in range(face_start, len(dxf_lines) - 1):
            if dxf_lines[index] in {"10", "20", "30"}:
                face_coordinates[dxf_lines[index]] = float(dxf_lines[index + 1])
        first_obj = tuple(float(value) for value in obj_vertices[0])
        first_dxf = tuple(face_coordinates[key] for key in ("10", "20", "30"))

        self.assertEqual(first_obj, (-0.5, -0.5, 3.0))
        self.assertEqual(first_dxf, first_obj)
        self.assertEqual(plan["storeys"][0]["rooms"][0]["contour"][0], [-0.5, -0.5])
        self.assertEqual(plan["storeys"][0]["elevation_m"], 3.0)
        self.assertEqual(dxf["origin_offset_m"], obj["origin_offset_m"])
        self.assertEqual(obj["coordinate_transform"].origin_basis, "selected_room_bounds_center")

class StfExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ifc_path = os.path.join(self.temp_dir.name, "room.ifc")
        create_geometry_ifc(
            self.ifc_path,
            "METRE",
            None,
            (6.0, 4.0, 3.0),
            ifc_class="IfcSpace",
        )
        self.inspector = IfcModelInspector(self.ifc_path).load()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _add_ifc_footprint(self, *, storey_elevation: float, footprint_elevation: float) -> None:
        model = ifcopenshell.open(self.ifc_path)
        storey = model.by_type("IfcBuildingStorey")[0]
        storey.Elevation = storey_elevation
        space = model.by_type("IfcSpace")[0]
        points = [
            model.create_entity("IfcCartesianPoint", Coordinates=coordinates)
            for coordinates in (
                (0.0, 0.0, footprint_elevation),
                (6.0, 0.0, footprint_elevation),
                (6.0, 4.0, footprint_elevation),
                (0.0, 4.0, footprint_elevation),
                (0.0, 0.0, footprint_elevation),
            )
        ]
        polyline = model.create_entity("IfcPolyline", Points=points)
        curve_set = model.create_entity("IfcGeometricCurveSet", Elements=[polyline])
        context = model.by_type("IfcGeometricRepresentationContext")[0]
        footprint = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="FootPrint",
            RepresentationType="GeometricCurveSet",
            Items=[curve_set],
        )
        space.Representation.Representations = [
            *space.Representation.Representations,
            footprint,
        ]
        model.write(self.ifc_path)

    def test_uses_ifc_footprint_when_body_floor_disagrees_with_storey(self) -> None:
        self._add_ifc_footprint(storey_elevation=0.5, footprint_elevation=0.5)
        inspector = IfcModelInspector(self.ifc_path).load()
        room = DialuxStfExporter(inspector).extract_rooms()[0]
        self.assertAlmostEqual(room["floor_z_m"], 0.5)
        self.assertEqual(
            room["contour_m"],
            [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
        )

    def test_ignores_ifc_footprint_when_body_floor_matches_storey(self) -> None:
        self._add_ifc_footprint(storey_elevation=0.0, footprint_elevation=0.5)
        inspector = IfcModelInspector(self.ifc_path).load()
        room = DialuxStfExporter(inspector).extract_rooms()[0]
        self.assertAlmostEqual(room["floor_z_m"], 0.0)
        self.assertEqual(room["geometry_diagnostics"]["selected_contour_source"], "body_floor_mesh")
        self.assertEqual(room["geometry_diagnostics"]["warnings"], [])

    def test_reports_when_body_and_ifc_footprint_both_disagree_with_storey(self) -> None:
        self._add_ifc_footprint(storey_elevation=1.0, footprint_elevation=0.5)
        inspector = IfcModelInspector(self.ifc_path).load()
        room = DialuxStfExporter(inspector).extract_rooms()[0]
        self.assertAlmostEqual(room["floor_z_m"], 0.0)
        self.assertEqual(room["geometry_diagnostics"]["selected_contour_source"], "body_floor_mesh")
        self.assertEqual(len(room["geometry_diagnostics"]["warnings"]), 1)
        self.assertIn("both disagree with assigned storey", room["geometry_diagnostics"]["warnings"][0])

    def test_creates_native_stf_room_from_ifc_footprint(self) -> None:
        output = os.path.join(self.temp_dir.name, "building.stf")
        result = DialuxStfExporter(self.inspector).export(output)
        stf_data = Path(result["stf_path"]).read_bytes()
        self.assertIn(b"[VERSION]\r\nSTFF=1.0.5", stf_data)
        self.assertIn(b"Room1=ROOM.R1", stf_data)
        self.assertIn(b"[ROOM.R1]\r\nName=Meeting room\r\nHeight=3", stf_data)
        self.assertIn(b"WorkingPlane=0.85", stf_data)
        self.assertIn(b"NrPoints=4", stf_data)
        self.assertIn("File > Import > STF", result["manual_actions"][0])

        room_points = []
        in_room = False
        for line in stf_data.decode("latin-1").splitlines():
            if line == "[ROOM.R1]":
                in_room = True
            elif line.startswith("[") and line != "[ROOM.R1]":
                in_room = False
            elif in_room and line.startswith("Point"):
                room_points.append(tuple(float(value) for value in line.split("=", 1)[1].split()))
        area = abs(
            sum(
                room_points[index][0] * room_points[(index + 1) % len(room_points)][1]
                - room_points[(index + 1) % len(room_points)][0] * room_points[index][1]
                for index in range(len(room_points))
            )
            / 2
        )
        self.assertAlmostEqual(area, 24.0, places=5)
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["rooms"][0]["source_storey"], "Ground Floor")
        self.assertEqual(metadata["rooms"][0]["height_m"], 3.0)
        self.assertIn("cannot create native DIALux storeys", " ".join(metadata["limitations"]))

    def test_reuses_extracted_room_contours_for_stf_export(self) -> None:
        exporter = DialuxStfExporter(self.inspector)
        records = exporter.extract_rooms()
        result = exporter.export_room_records(
            os.path.join(self.temp_dir.name, "reused_rooms.stf"),
            records,
            selected_storeys=["Ground Floor"],
        )
        self.assertEqual(result["room_count"], 1)
        self.assertEqual(result["storeys"], ["Ground Floor"])

    def test_rejects_spaces_without_3d_representation(self) -> None:
        inspector = IfcModelInspector(self.inspector.file_path).load()
        inspector.ifc_file.by_type("IfcSpace")[0].Representation = None
        with self.assertRaisesRegex(ValueError, "no usable IFC 3D representation"):
            DialuxStfExporter(inspector).export(os.path.join(self.temp_dir.name, "invalid.stf"))

    def test_reflectance_values_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "[Ww]all reflectance"):
            DialuxStfExporter(self.inspector, wall_reflectance=1.2)

    def test_room_labels_are_safe_unique_and_length_limited(self) -> None:
        rooms = [
            {
                "name": "Room [A]=1",
                "source_storey": "Ground=Floor",
                "ifc_global_id": "000000000000000000000001",
                "contour_m_stf": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                "height_m": 3.0,
            },
            {
                "name": "Room [A]=1",
                "source_storey": "Ground=Floor",
                "ifc_global_id": "000000000000000000000002",
                "contour_m_stf": [(2.0, 0.0), (3.0, 0.0), (3.0, 1.0)],
                "height_m": 3.0,
            },
            {
                "name": "Very long room name " * 8 + "😀",
                "source_storey": "Upper",
                "ifc_global_id": "000000000000000000000003",
                "contour_m_stf": [(4.0, 0.0), (5.0, 0.0), (5.0, 1.0)],
                "height_m": 3.0,
            },
        ]
        lines, _metadata = DialuxStfExporter(self.inspector)._build_stf(rooms)
        names = []
        in_room = False
        for line in lines:
            if line.startswith("[ROOM."):
                in_room = True
            elif line.startswith("Name=") and in_room:
                names.append(line.partition("=")[2])
        self.assertEqual(len(names), 3)
        self.assertEqual(len({name.casefold() for name in names}), 3)
        self.assertTrue(all(0 < len(name) <= 32 for name in names))
        self.assertTrue(all(not any(delimiter in name for delimiter in "=[]") for name in names))

    def test_rejects_multiple_source_storeys_before_export(self) -> None:
        model = self.inspector.ifc_file
        model.create_entity(
            "IfcSpace",
            GlobalId="0000000000000000000009",
            Name="Upper room",
            LongName="Upper room",
            CompositionType="ELEMENT",
        )
        self.inspector.element_to_storey["0000000000000000000002"] = "Ground"
        self.inspector.element_to_storey["0000000000000000000009"] = "Upper"
        self.inspector.storeys.extend(
            [
                {"name": "Ground", "elevation": 0.0},
                {"name": "Upper", "elevation": 3.0},
            ]
        )
        with self.assertRaisesRegex(ValueError, "cannot preserve IFC storey elevations"):
            DialuxStfExporter(self.inspector).export(
                os.path.join(self.temp_dir.name, "multi_storey.stf"),
                selected_storeys=["Ground", "Upper"],
            )

    def test_rejects_overlapping_room_footprints(self) -> None:
        rooms = [
            {
                "name": "Room A",
                "source_storey": "Ground",
                "contour_m": [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
            },
            {
                "name": "Room B",
                "source_storey": "Ground",
                "contour_m": [(3.0, 0.0), (6.0, 0.0), (6.0, 4.0), (3.0, 4.0)],
            },
        ]
        with self.assertRaisesRegex(ValueError, "Room A.*Room B.*4.000 m²"):
            DialuxStfExporter._validate_no_overlapping_room_footprints(rooms)

    def test_adjacent_room_footprints_do_not_count_as_overlapping(self) -> None:
        rooms = [
            {
                "name": "Room A",
                "source_storey": "Ground",
                "contour_m": [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
            },
            {
                "name": "Room B",
                "source_storey": "Ground",
                "contour_m": [(4.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0)],
            },
        ]
        DialuxStfExporter._validate_no_overlapping_room_footprints(rooms)

    def test_keeps_source_storey_coordinates_without_sideways_offsets(self) -> None:
        exporter = DialuxStfExporter(self.inspector)
        rooms = [
            {
                "name": "Ground room",
                "source_storey": "Ground",
                "contour_m": [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
            },
            {
                "name": "Upper room",
                "source_storey": "Level 1",
                "contour_m": [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)],
            },
        ]
        exporter._align_to_geometry_origin(rooms)
        self.assertEqual(rooms[0]["storey_layout_offset_x_m"], 0.0)
        self.assertEqual(rooms[1]["contour_m"][0], (0.0, 0.0))
        self.assertEqual(rooms[1]["storey_layout_offset_x_m"], 0.0)
        self.assertEqual(rooms[1]["contour_m_stf"][0][0], 0.0)

    def test_room_contours_share_the_rebased_obj_origin(self) -> None:
        rooms = [
            {
                "name": "Room",
                "source_storey": "Ground",
                "contour_m": [(100.0, 200.0), (106.0, 200.0), (106.0, 204.0), (100.0, 204.0)],
            }
        ]
        DialuxStfExporter(self.inspector)._align_to_geometry_origin(
            rooms,
            coordinate_transform=CoordinateTransform(
                origin_offset_m=(99.0, 199.0, 0.0)
            ),
        )
        self.assertEqual(rooms[0]["contour_m_stf"][0], (1.0, 1.0))
        self.assertEqual(rooms[0]["source_offset_xy_m"], [99.0, 199.0])


class NativeProjectPlanTests(unittest.TestCase):
    def test_native_geometry_plan_tessellates_products_with_shared_transform(self) -> None:
        class Product:
            GlobalId = "Wall-GlobalId"
            Name = "North wall"
            Representation = object()
            def id(self): return 11
            def is_a(self, name=None): return "IfcWall" if name is None else name == "IfcWall"

        product = Product()
        inspector = SimpleNamespace(
            project_name="School", ifc_file=SimpleNamespace(by_type=lambda name: [product] if name == "IfcProduct" else []),
            element_to_storey={"Wall-GlobalId": "Level 1"}, unit_scale_to_meters=0.001,
            get_tessellation_settings=lambda: object(),
        )
        record = {
            "name": "Room", "source_storey": "Level 1", "floor_z_m": 0.0, "height_m": 3.0,
            "contour_m": [(1000.0, 2000.0), (3000.0, 2000.0), (3000.0, 4000.0)],
        }
        shape = SimpleNamespace(geometry=SimpleNamespace(
            verts=(1000.0, 2000.0, 3000.0, 2000.0, 2000.0, 3000.0, 1000.0, 3000.0, 3000.0),
            faces=(0, 1, 2),
        ))
        with mock.patch("src.native_exporter.ifcopenshell.geom.create_shape", return_value=shape):
            plan = build_native_model_plan(
                inspector, [record], geometry_origin_m=(1.0, 2.0, 0.0)
            )
        self.assertEqual(len(plan["native_elements"]), 1)
        mesh = plan["native_elements"][0]
        self.assertEqual(mesh["ifc_global_id"], "Wall-GlobalId")
        self.assertEqual(mesh["ifc_type"], "IfcWall")
        self.assertEqual(mesh["triangles"], [[(0.0, 0.0, 3.0), (1.0, 0.0, 3.0), (0.0, 1.0, 3.0)]])

    def test_native_host_requires_a_bundled_dotnet_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = Path(directory) / "DialuxIfcNativeHost.exe"
            runtime_config = host.with_name("DialuxIfcNativeHost.runtimeconfig.json")
            runtime_config.write_text(
                json.dumps({"runtimeOptions": {"includedFrameworks": [{"name": "Microsoft.NETCore.App"}]}}),
                encoding="utf-8",
            )
            for name in ("coreclr.dll", "hostfxr.dll", "hostpolicy.dll"):
                (Path(directory) / name).touch()
            self.assertTrue(DialuxNativeProjectExporter._is_self_contained_native_host(host))

            runtime_config.write_text(
                json.dumps({"runtimeOptions": {"frameworks": [{"name": "Microsoft.NETCore.App"}]}}),
                encoding="utf-8",
            )
            self.assertFalse(DialuxNativeProjectExporter._is_self_contained_native_host(host))

    def test_reads_ifc_site_geolocation_and_converts_dms_to_degrees(self) -> None:
        site = SimpleNamespace(
            Name="Example project site",
            RefLatitude=(40, 42, 46, 800000),
            RefLongitude=(-74, -0, -21, -600000),
        )
        inspector = SimpleNamespace(
            project_name="School",
            ifc_file=SimpleNamespace(by_type=lambda name: [site] if name == "IfcSite" else []),
        )
        record = {
            "name": "Room",
            "source_storey": "Level 1",
            "floor_z_m": 0.0,
            "height_m": 3.0,
            "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
        }
        plan = build_native_model_plan(inspector, [record])
        self.assertEqual(plan["site"]["location"], "Example project site")
        self.assertAlmostEqual(plan["site"]["latitude_degrees"], 40.713)
        self.assertAlmostEqual(plan["site"]["longitude_degrees"], -74.006)

    def test_native_room_plan_preserves_ifc_identity_and_geometry_warnings(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        warning = "Body floor and IFC FootPrint disagree with the source storey."
        record = {
            "ifc_global_id": "2Yy123",
            "name": "Room",
            "source_storey": "Volume Modeling Reference 2",
            "floor_z_m": 3.9624,
            "height_m": 3.0,
            "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
            "geometry_diagnostics": {
                "selected_contour_source": "body_floor_mesh",
                "warnings": [warning],
            },
        }
        plan = build_native_model_plan(inspector, [record])
        room = plan["storeys"][0]["rooms"][0]
        self.assertEqual(room["ifc_global_id"], "2Yy123")
        self.assertEqual(room["source_ifc_storey"], "Volume Modeling Reference 2")
        self.assertEqual(plan["geometry_warnings"], [warning])

    def test_native_room_audit_names_are_unique_in_native_creation_order(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        records = [
            {
                "ifc_global_id": "Room-A",
                "name": "Room",
                "source_storey": "Level 1",
                "floor_z_m": 0.0,
                "height_m": 3.0,
                "contour_m": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
            },
            {
                "ifc_global_id": "Room-B",
                "name": "room",
                "source_storey": "Level 2",
                "floor_z_m": 4.0,
                "height_m": 3.0,
                "contour_m": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
            },
        ]
        plan = build_native_model_plan(inspector, records)
        planned_names = [
            room["name"]
            for storey in plan["storeys"]
            for room in storey["rooms"]
        ]
        self.assertEqual(planned_names, ["Room", "room (2)"])

    def test_native_room_audit_writes_global_ids_transform_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "model_room_audit.json"
            inspector = SimpleNamespace(
                file_path="school.ifc",
                schema="IFC2X3",
            )
            plan = {
                "coordinate_transform": {"origin_basis": "selected_room_bounds_center"},
                "geometry_warnings": ["Review source footprint."],
                "storeys": [
                    {
                        "name": "Level 1",
                        "rooms": [
                            {
                                "ifc_global_id": "2Yy123",
                                "source_name": "Room",
                                "source_ifc_storey": "Level 1",
                                "name": "Room",
                                "floor_z_m": 0.0,
                                "height_m": 3.0,
                                "geometry_diagnostics": {"warnings": ["Review source footprint."]},
                                "contour": [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]],
                            }
                        ],
                    }
                ],
            }
            verified_storeys = [{"name": "Level 1", "rooms": ["Room"]}]
            DialuxNativeProjectExporter._write_room_audit(
                audit_path,
                inspector,
                Path(directory) / "model.evo",
                plan,
                verified_storeys,
            )
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertEqual(audit["rooms"][0]["ifc_global_id"], "2Yy123")
        self.assertEqual(audit["rooms"][0]["native_storey"], "Level 1")
        self.assertEqual(audit["geometry_warnings"], ["Review source footprint."])
        self.assertEqual(audit["coordinate_transform"]["origin_basis"], "selected_room_bounds_center")

    def test_rejects_invalid_ifc_site_geolocation(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid geographic range"):
            _compound_angle_to_degrees((91, 0, 0, 0), "latitude")

    @mock.patch("src.dialux_bridge.launch_dialux")
    @mock.patch("src.dialux_bridge.is_dialux_process_running")
    @mock.patch("src.dialux_bridge.activate_dialux")
    @mock.patch("src.dialux_bridge.copy_files_to_clipboard", return_value=True)
    def test_package_clipboard_handoff_does_not_activate_or_launch_dialux(
        self,
        copy_files: mock.Mock,
        activate: mock.Mock,
        process_running: mock.Mock,
        launch: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            obj_path = Path(directory) / "model.obj"
            obj_path.write_text("test", encoding="utf-8")
            result = send_to_dialux(str(obj_path), activate=False)
        self.assertTrue(result["copied"])
        self.assertFalse(result["dialux_activated"])
        self.assertFalse(result["dialux_launched"])
        copy_files.assert_called_once()
        activate.assert_not_called()
        process_running.assert_not_called()
        launch.assert_not_called()

    def test_preserves_storey_elevations_and_rebases_room_contours(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        records = [
            {
                "name": "Room 1",
                "source_storey": "Level 1",
                "source_storey_elevation_m": 0.0,
                "floor_z_m": 0.0,
                "height_m": 3.0,
                "contour_m": [(10.0, 20.0), (12.0, 20.0), (12.0, 23.0)],
            },
            {
                "name": "Room 2",
                "source_storey": "Level 2",
                "source_storey_elevation_m": 4.2,
                "floor_z_m": 4.2,
                "height_m": 2.8,
                "contour_m": [(10.0, 20.0), (13.0, 20.0), (13.0, 24.0)],
            },
        ]
        plan = build_native_model_plan(
            inspector,
            records,
            geometry_origin_m=(3.0, 5.0, 1.2),
            workplane_m=0.8,
        )
        self.assertEqual(plan["project_name"], "School")
        self.assertEqual([storey["name"] for storey in plan["storeys"]], ["Level 1", "Level 2"])
        self.assertAlmostEqual(plan["storeys"][0]["elevation_m"], -1.2)
        self.assertAlmostEqual(plan["storeys"][1]["elevation_m"], 3.0)
        self.assertEqual(plan["storeys"][1]["rooms"][0]["contour"][0], [7.0, 15.0])
        self.assertEqual(plan["storeys"][1]["height_m"], 2.8)
        self.assertEqual(plan["workplane_m"], 0.8)

    def test_rejects_rooms_without_storey_assignment(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        record = {
            "name": "Unassigned room",
            "source_storey": "Unassigned",
            "floor_z_m": 0.0,
            "height_m": 3.0,
            "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
        }
        with self.assertRaisesRegex(ValueError, "no IFC storey assignment"):
            build_native_model_plan(inspector, [record])

    def test_infers_missing_storey_elevation_from_room_floor(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        record = {
            "name": "Room",
            "source_storey": "Level 1",
            "source_storey_elevation_m": None,
            "floor_z_m": 1.25,
            "height_m": 3.0,
            "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
        }
        plan = build_native_model_plan(inspector, [record])
        self.assertAlmostEqual(plan["storeys"][0]["elevation_m"], 1.25)

    def test_room_floor_geometry_takes_precedence_over_mismatched_ifc_elevation(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        record = {
            "name": "Room",
            "source_storey": "Level 1",
            "source_storey_elevation_m": 0.0,
            "floor_z_m": 0.25,
            "height_m": 3.0,
            "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
        }
        plan = build_native_model_plan(inspector, [record])
        self.assertAlmostEqual(plan["storeys"][0]["elevation_m"], 0.25)
        self.assertAlmostEqual(plan["storeys"][0]["source_elevation_m"], 0.0)

    def test_merges_misassigned_room_into_unique_matching_storey(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        records = [
            {
                "name": "Level 2 room",
                "source_storey": "Level 2",
                "source_storey_elevation_m": 3.9624,
                "floor_z_m": 3.9624,
                "height_m": 3.0,
                "contour_m": [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0)],
            },
            {
                "name": "Reference-level room",
                "source_storey": "Volume Modeling Reference 2",
                "source_storey_elevation_m": 9.652,
                "floor_z_m": 3.9624,
                "height_m": 3.0,
                "contour_m": [(3.0, 0.0), (5.0, 0.0), (5.0, 2.0)],
            },
        ]
        plan = build_native_model_plan(inspector, records)
        self.assertEqual(len(plan["storeys"]), 1)
        self.assertEqual(plan["storeys"][0]["name"], "Level 2")
        self.assertEqual(
            {room["name"] for room in plan["storeys"][0]["rooms"]},
            {"Level 2 room", "Reference-level room"},
        )

    def test_rejects_rooms_with_incompatible_floor_elevations_on_one_storey(self) -> None:
        inspector = SimpleNamespace(project_name="School")
        records = [
            {
                "name": f"Room {index}",
                "source_storey": "Level 1",
                "source_storey_elevation_m": 0.0,
                "floor_z_m": floor_z,
                "height_m": 3.0,
                "contour_m": [(index * 3.0, 0.0), (index * 3.0 + 2.0, 0.0), (index * 3.0 + 2.0, 2.0)],
            }
            for index, floor_z in enumerate((0.0, 0.1))
        ]
        with self.assertRaisesRegex(ValueError, "vary by more than 2 cm"):
            build_native_model_plan(inspector, records)

    def test_native_readback_requires_site_location_for_construction_mode(self) -> None:
        plan = {
            "storeys": [
                {"name": "Level 1", "elevation_m": 0.0, "rooms": [{"name": "Room"}]},
            ],
        }
        readback = {
            "buildings": [
                {"storeys": [{"name": "Level 1", "elevation_m": 0.0, "rooms": ["Room"]}]},
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "no site location"):
            DialuxNativeProjectExporter._verify_readback(plan, readback)

    def test_native_readback_requires_a_boundary_contour_for_every_room(self) -> None:
        plan = {
            "site": {"location": "Test site", "latitude_degrees": None, "longitude_degrees": None},
            "storeys": [{
                "name": "Level 1", "elevation_m": 0.0, "source_elevation_m": 0.0,
                "elevation_basis": "room geometry", "rooms": [{"name": "Room A"}, {"name": "Room B"}],
            }],
        }
        readback = {
            "location": "Test site", "buildings": [{"storeys": [{
                "name": "Level 1", "elevation_m": 0.0, "rooms": ["Room A", "Room B"],
                "room_floor_elevations_m": [0.0, 0.0],
                "storey_elements": [{"contour_count": 2, "associated_space_count": 2}],
            }]}],
        }
        verified = DialuxNativeProjectExporter._verify_readback(plan, readback)
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["storey_elements"][0]["associated_space_count"], 2)

        readback["buildings"][0]["storeys"][0]["storey_elements"][0]["associated_space_count"] = 1
        with self.assertRaisesRegex(RuntimeError, "native room-boundary contours"):
            DialuxNativeProjectExporter._verify_readback(plan, readback)

    def test_native_readback_requires_each_requested_ifc_mesh(self) -> None:
        plan = {
            "site": {"location": "Test site", "latitude_degrees": None, "longitude_degrees": None},
            "native_elements": [{"storey": "Level 1"}],
            "storeys": [{"name": "Level 1", "elevation_m": 0.0, "source_elevation_m": 0.0,
                         "elevation_basis": "room geometry", "rooms": [{"name": "Room A"}]}],
        }
        storey = {
            "name": "Level 1", "elevation_m": 0.0, "rooms": ["Room A"],
            "room_floor_elevations_m": [0.0],
            "storey_elements": [{"contour_count": 1, "associated_space_count": 1}],
            "contained_elements": [{"is_generic_geometry": True}],
        }
        readback = {"location": "Test site", "buildings": [{"storeys": [storey]}]}
        self.assertEqual(len(DialuxNativeProjectExporter._verify_readback(plan, readback)), 1)
        storey["contained_elements"] = []
        with self.assertRaisesRegex(RuntimeError, "native IFC mesh elements"):
            DialuxNativeProjectExporter._verify_readback(plan, readback)


class ObjExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ifc_path = os.path.join(self.temp_dir.name, "minimal_mm.ifc")
        create_minimal_ifc(self.ifc_path)
        self.inspector = IfcModelInspector(self.ifc_path).load()
        self.output_path = os.path.join(self.temp_dir.name, "model.obj")
        self.shape = SimpleNamespace(
            geometry=SimpleNamespace(
                verts=(1000.0, 2000.0, 3000.0, 2000.0, 2000.0, 3000.0, 1000.0, 3000.0, 3000.0),
                faces=(0, 1, 2),
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape")
    def test_exports_meter_scaled_mesh_and_room_metadata(self, create_shape: mock.Mock) -> None:
        create_shape.return_value = self.shape
        result = DialuxObjExporter(self.inspector).export(self.output_path, include_spaces=True)
        self.assertEqual(result["total_vertices"], 6)
        self.assertEqual(result["total_faces"], 2)
        self.assertAlmostEqual(result["effective_scale"], 0.001)
        self.assertEqual(result["origin_offset_m"], [1.0, 2.0, 3.0])

        obj_text = Path(result["obj_path"]).read_text(encoding="utf-8")
        self.assertIn("v 0 0 0\n", obj_text)
        self.assertIn("v 1 0 0\n", obj_text)
        self.assertIn("mtllib model.mtl", obj_text)
        self.assertIn("o IfcSpace_Room_101_", obj_text)
        self.assertTrue(Path(result["mtl_path"]).is_file())
        self.assertTrue(Path(result["rooms_path"]).is_file())

        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertAlmostEqual(metadata["source_to_meters"], 0.001)
        self.assertEqual(metadata["coordinate_transform"]["origin_basis"], "first_exported_geometry_vertex")
        self.assertEqual(metadata["geometry"]["bounds_min"], [0.0, 0.0, 0.0])
        self.assertEqual(metadata["geometry"]["bounds_max"], [1.0, 1.0, 0.0])
        self.assertEqual(result["geometry_bounds"]["unit"], "metres")
        self.assertEqual(metadata["space_boundaries"][0]["space_id"], "0000000000000000000004")
        self.assertEqual(metadata["exported_elements"][0]["property_sets"], {})
        with open(result["rooms_path"], encoding="utf-8-sig", newline="") as rooms_file:
            rooms = list(csv.DictReader(rooms_file))
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]["name"], "Room 101")
        self.assertEqual(rooms[0]["boundary_count"], "1")

    @mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape")
    def test_space_volumes_are_not_added_to_obj_by_default(self, create_shape: mock.Mock) -> None:
        create_shape.return_value = self.shape
        result = DialuxObjExporter(self.inspector).export(self.output_path)
        self.assertEqual(result["total_faces"], 1)
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["ifc_type"] for item in metadata["exported_elements"]], ["IfcWall"])
        self.assertEqual([item["ifc_type"] for item in metadata["rooms"]], ["IfcSpace"])
        with open(result["rooms_path"], encoding="utf-8-sig", newline="") as rooms_file:
            self.assertEqual(len(list(csv.DictReader(rooms_file))), 1)

    @mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape")
    def test_ifc_surface_styles_are_written_and_bound_per_face(self, create_shape: mock.Mock) -> None:
        styles = [
            SimpleNamespace(
                name="Concrete",
                diffuse=SimpleNamespace(components=(0.2, 0.3, 0.4)),
                specular=SimpleNamespace(components=(0.1, 0.1, 0.1)),
                transparency=0.0,
            ),
            SimpleNamespace(
                name="Blue glazing",
                diffuse=SimpleNamespace(components=(0.1, 0.25, 0.8)),
                specular=SimpleNamespace(components=(0.7, 0.7, 0.8)),
                transparency=0.35,
            ),
        ]
        create_shape.return_value = SimpleNamespace(
            geometry=SimpleNamespace(
                verts=(0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0),
                faces=(0, 1, 2, 0, 2, 3),
                materials=styles,
                material_ids=(0, 1),
            )
        )
        result = DialuxObjExporter(self.inspector).export(
            self.output_path,
            selected_categories=["IfcWall"],
        )
        obj_text = Path(result["obj_path"]).read_text(encoding="utf-8")
        material_switches = [line for line in obj_text.splitlines() if line.startswith("usemtl ")]
        self.assertEqual(len(material_switches), 2)
        self.assertIn("IFC_Concrete_334C66_100", material_switches[0])
        self.assertIn("IFC_Blue_glazing_1A40CC_65", material_switches[1])

        mtl_text = Path(result["mtl_path"]).read_text(encoding="utf-8")
        self.assertIn("Kd 0.2000 0.3000 0.4000", mtl_text)
        self.assertIn("Kd 0.1000 0.2500 0.8000", mtl_text)
        self.assertIn("d 0.6500", mtl_text)

    @mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape")
    def test_space_toggle_excludes_room_geometry_and_schedule_rows(self, create_shape: mock.Mock) -> None:
        create_shape.return_value = self.shape
        result = DialuxObjExporter(self.inspector).export(
            self.output_path,
            include_spaces=False,
        )
        self.assertEqual(result["total_faces"], 1)
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["ifc_type"] for item in metadata["exported_elements"]], ["IfcWall"])
        self.assertEqual([item["ifc_type"] for item in metadata["rooms"]], ["IfcSpace"])
        with open(result["rooms_path"], encoding="utf-8-sig", newline="") as rooms_file:
            self.assertEqual(len(list(csv.DictReader(rooms_file))), 1)

    @mock.patch("src.obj_exporter.ifcopenshell.geom.create_shape")
    def test_cancellation_leaves_no_partial_output(self, create_shape: mock.Mock) -> None:
        create_shape.return_value = self.shape
        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaises(InterruptedError):
            DialuxObjExporter(self.inspector).export(
                self.output_path,
                cancel_event=cancel_event,
            )
        self.assertFalse(os.path.exists(self.output_path))
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, "model.mtl")))

    def test_rejects_non_positive_scale(self) -> None:
        with self.assertRaises(ValueError):
            DialuxObjExporter(self.inspector).export(self.output_path, scale_factor=0)


class DialuxDetectionTests(unittest.TestCase):
    def test_detection_is_safe_without_windows_registry(self) -> None:
        with mock.patch("src.dialux_bridge.os.name", "posix"):
            self.assertIsNone(find_dialux_executable())


if __name__ == "__main__":
    unittest.main()
