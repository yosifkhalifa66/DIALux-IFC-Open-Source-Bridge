"""
3D DXF Exporter for DIALux evo CAD Import.
Exports 3D geometry as 3DFACE entities organized by layer.
"""
import os
import time
from typing import List, Optional, Callable, Dict, Any
import ifcopenshell
import ifcopenshell.geom
from .utils import logger, sanitize_filename
from .ifc_parser import IfcModelInspector

class DialuxDxfExporter:
    def __init__(self, inspector: IfcModelInspector):
        self.inspector = inspector

    def export(
        self,
        output_dxf_path: str,
        selected_categories: Optional[List[str]] = None,
        selected_storeys: Optional[List[str]] = None,
        scale_factor: Optional[float] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """Convert IFC geometry to AutoCAD 3D DXF format."""
        start_time = time.time()
        os.makedirs(os.path.dirname(os.path.abspath(output_dxf_path)), exist_ok=True)
        
        scale = scale_factor if scale_factor is not None else self.inspector.unit_scale_to_meters
        geom_settings = self.inspector.get_tessellation_settings()
        
        elements_to_export = []
        for cls_name, elem_list in self.inspector.elements_by_class.items():
            if selected_categories and cls_name not in selected_categories:
                continue
            for elem in elem_list:
                parent_storey = self.inspector.element_to_storey.get(elem.GlobalId, "Default Storey")
                if selected_storeys and parent_storey not in selected_storeys:
                    continue
                elements_to_export.append((cls_name, parent_storey, elem))
                
        total_elements = len(elements_to_export)
        total_faces = 0
        
        with open(output_dxf_path, "w", encoding="utf-8") as dxf:
            # Minimal DXF R12 Header
            dxf.write("0\nSECTION\n2\nHEADER\n0\nENDSEC\n")
            dxf.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")
            dxf.write("0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n")
            dxf.write("0\nSECTION\n2\nENTITIES\n")
            
            for idx, (cls_name, storey_name, elem) in enumerate(elements_to_export):
                layer = sanitize_filename(f"{storey_name}_{cls_name}")[:31]
                if progress_callback:
                    progress_callback(idx + 1, total_elements, f"DXF: {cls_name}")
                    
                try:
                    shape = ifcopenshell.geom.create_shape(geom_settings, elem)
                except Exception:
                    continue
                    
                verts = shape.geometry.verts
                faces = shape.geometry.faces
                if not verts or not faces:
                    continue
                    
                for f_i in range(0, len(faces), 3):
                    i1, i2, i3 = faces[f_i] * 3, faces[f_i + 1] * 3, faces[f_i + 2] * 3
                    
                    x1, y1, z1 = verts[i1] * scale, verts[i1 + 1] * scale, verts[i1 + 2] * scale
                    x2, y2, z2 = verts[i2] * scale, verts[i2 + 1] * scale, verts[i2 + 2] * scale
                    x3, y3, z3 = verts[i3] * scale, verts[i3 + 1] * scale, verts[i3 + 2] * scale
                    
                    # 3DFACE entity
                    dxf.write(f"0\n3DFACE\n8\n{layer}\n")
                    dxf.write(f"10\n{x1:.4f}\n20\n{y1:.4f}\n30\n{z1:.4f}\n")
                    dxf.write(f"11\n{x2:.4f}\n21\n{y2:.4f}\n31\n{z2:.4f}\n")
                    dxf.write(f"12\n{x3:.4f}\n22\n{y3:.4f}\n32\n{z3:.4f}\n")
                    dxf.write(f"13\n{x3:.4f}\n23\n{y3:.4f}\n33\n{z3:.4f}\n")
                    total_faces += 1
                    
            dxf.write("0\nENDSEC\n0\nEOF\n")
            
        elapsed = time.time() - start_time
        return {
            "dxf_path": output_dxf_path,
            "total_faces": total_faces,
            "elapsed_seconds": elapsed,
        }
