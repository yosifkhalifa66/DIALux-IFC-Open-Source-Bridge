import os
import ifcopenshell
import ifcopenshell.geom

def test_obj_export():
    ifc_path = r"D:\dialux ifc drag-drop\tests\sample_office.ifc"
    obj_path = r"D:\dialux ifc drag-drop\tests\sample_office.obj"
    mtl_path = r"D:\dialux ifc drag-drop\tests\sample_office.mtl"
    
    f = ifcopenshell.open(ifc_path)
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    
    products = f.by_type("IfcProduct")
    
    # Write MTL
    with open(mtl_path, "w", encoding="utf-8") as mtl:
        mtl.write("# DIALux evo Material Library\n\n")
        mtl.write("newmtl Material_IfcWall\n")
        mtl.write("Ka 0.2 0.2 0.2\nKd 0.75 0.75 0.75\nKs 0.1 0.1 0.1\nNs 10.0\nillum 2\n\n")
        mtl.write("newmtl Material_IfcSlab\n")
        mtl.write("Ka 0.2 0.2 0.2\nKd 0.35 0.35 0.35\nKs 0.05 0.05 0.05\nNs 5.0\nillum 2\n\n")
        mtl.write("newmtl Material_Default\n")
        mtl.write("Ka 0.2 0.2 0.2\nKd 0.6 0.6 0.6\nKs 0.1 0.1 0.1\nNs 10.0\nillum 2\n\n")
        
    # Write OBJ
    vertex_offset = 1
    with open(obj_path, "w", encoding="utf-8") as obj:
        obj.write("# Converted by DIALux IFC Bridge for DIALux evo\n")
        obj.write(f"mtllib {os.path.basename(mtl_path)}\n\n")
        
        for p in products:
            if not p.Representation:
                continue
            try:
                shape = ifcopenshell.geom.create_shape(s, p)
            except Exception as e:
                continue
                
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            
            p_class = p.is_a()
            p_name = (p.Name or p_class).replace(" ", "_")
            obj.write(f"o {p_class}_{p_name}_{p.GlobalId}\n")
            obj.write(f"g {p_class}\n")
            
            mat_name = f"Material_{p_class}"
            obj.write(f"usemtl {mat_name}\n")
            
            # Write vertices
            for i in range(0, len(verts), 3):
                x, y, z = verts[i], verts[i+1], verts[i+2]
                obj.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
                
            # Write faces (1-based index)
            for i in range(0, len(faces), 3):
                f1 = faces[i] + vertex_offset
                f2 = faces[i+1] + vertex_offset
                f3 = faces[i+2] + vertex_offset
                obj.write(f"f {f1} {f2} {f3}\n")
                
            vertex_offset += len(verts) // 3
            obj.write("\n")
            
    print(f"OBJ exported successfully: {obj_path} ({os.path.getsize(obj_path)} bytes)")

if __name__ == "__main__":
    test_obj_export()
