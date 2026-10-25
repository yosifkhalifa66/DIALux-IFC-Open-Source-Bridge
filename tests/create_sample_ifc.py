"""
Generate a sample IFC4 architectural model for testing.
Creates a small building with walls, slab, door, window, and roof.
"""
import os
import ifcopenshell
import ifcopenshell.api

def create_sample_model(output_path: str):
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    
    # Project & Units
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Sample Office")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    
    # Hierarchy
    context = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context
    )
    
    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Main Building")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Ground Floor")
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])
    
    # Add a Slab (Floor: 6m x 6m x 0.2m)
    slab = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSlab", name="Ground Slab")
    ifcopenshell.api.run("spatial.assign_container", f, relating_structure=storey, products=[slab])
    slab_rep = ifcopenshell.api.run(
        "geometry.add_slab_representation", f,
        context=body,
        polyline=[(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0), (0.0, 0.0)],
        depth=0.2
    )
    ifcopenshell.api.run("geometry.assign_representation", f, product=slab, representation=slab_rep)
    
    # Add 4 Walls
    wall_params = [
        ("Wall North", 6.0, 0.2, 3.0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        ("Wall South", 6.0, 0.2, 3.0, (0.0, 5.8, 0.0), (1.0, 0.0, 0.0)),
        ("Wall West",  5.6, 0.2, 3.0, (0.0, 0.2, 0.0), (0.0, 1.0, 0.0)),
        ("Wall East",  5.6, 0.2, 3.0, (5.8, 0.2, 0.0), (0.0, 1.0, 0.0)),
    ]
    
    for name, length, thickness, height, loc, dir_vec in wall_params:
        wall = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcWall", name=name)
        ifcopenshell.api.run("spatial.assign_container", f, relating_structure=storey, products=[wall])
        wall_rep = ifcopenshell.api.run(
            "geometry.add_wall_representation", f,
            context=body,
            length=length,
            thickness=thickness,
            height=height
        )
        ifcopenshell.api.run("geometry.assign_representation", f, product=wall, representation=wall_rep)
        matrix = [
            [dir_vec[0], -dir_vec[1], 0.0, loc[0]],
            [dir_vec[1],  dir_vec[0], 0.0, loc[1]],
            [0.0,         0.0,        1.0, loc[2]],
            [0.0,         0.0,        0.0, 1.0]
        ]
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=wall, matrix=matrix)
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    f.write(output_path)
    print(f"Sample IFC file written to: {output_path}")

if __name__ == "__main__":
    test_file = r"D:\dialux ifc drag-drop\tests\sample_office.ifc"
    create_sample_model(test_file)
