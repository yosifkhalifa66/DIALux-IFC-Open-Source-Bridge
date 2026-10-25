import ifcopenshell
import ifcopenshell.geom

def test():
    ifc_path = r"D:\dialux ifc drag-drop\tests\sample_office.ifc"
    f = ifcopenshell.open(ifc_path)
    s = ifcopenshell.geom.settings()
    s.set(s.USE_WORLD_COORDS, True)
    
    products = f.by_type("IfcProduct")
    print(f"Total IFC products: {len(products)}")
    
    for p in products:
        if p.Representation:
            try:
                shape = ifcopenshell.geom.create_shape(s, p)
                verts_count = len(shape.geometry.verts) // 3
                faces_count = len(shape.geometry.faces) // 3
                print(f"[{p.is_a()}] {p.Name or 'Unnamed'} -> {verts_count} vertices, {faces_count} triangles")
            except Exception as e:
                print(f"Error creating shape for {p}: {e}")

if __name__ == "__main__":
    test()
