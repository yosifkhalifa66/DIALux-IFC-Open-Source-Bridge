"""
Advanced Wavefront OBJ & MTL Exporter customized for DIALux evo.
Handles unit scaling (to Meters), group hierarchy, storey splitting,
and photometric surface reflectance properties.
"""
import os
import time
from typing import List, Dict, Any, Optional, Callable
import ifcopenshell
import ifcopenshell.geom
from .utils import logger, DEFAULT_MATERIALS, sanitize_filename
from .ifc_parser import IfcModelInspector

class DialuxObjExporter:
    def __init__(self, inspector: IfcModelInspector):
        self.inspector = inspector
        self.materials_written: Dict[str, Dict[str, Any]] = {}

    def export(
        self,
        output_obj_path: str,
        selected_categories: Optional[List[str]] = None,
        selected_storeys: Optional[List[str]] = None,
        scale_factor: Optional[float] = None,
        group_by: str = "storey", # 'storey', 'category', 'both'
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Convert selected IFC elements into DIALux evo OBJ & MTL files.
        """
        start_time = time.time()
        os.makedirs(os.path.dirname(os.path.abspath(output_obj_path)), exist_ok=True)
        
        # Scaling: default to the detected scale factor to meters
        scale = scale_factor if scale_factor is not None else self.inspector.unit_scale_to_meters
        
        # Prepare file names
        base_name, _ = os.path.splitext(output_obj_path)
        mtl_path = base_name + ".mtl"
        mtl_filename = os.path.basename(mtl_path)
        
        # Determine elements to export
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
        if total_elements == 0:
            raise ValueError("No elements match the selected categories and storeys.")
            
        logger.info(f"Starting OBJ export: {total_elements} elements, scale={scale}")
        
        geom_settings = self.inspector.get_tessellation_settings()
        
        vertex_offset = 1
        total_vertices = 0
        total_faces = 0
        self.materials_written = {}
        
        with open(output_obj_path, "w", encoding="utf-8") as obj_file:
            # OBJ Header
            obj_file.write("# ------------------------------------------------------------\n")
            obj_file.write("# Exported by DIALux IFC Bridge for DIALux evo\n")
            obj_file.write(f"# Project: {self.inspector.project_name}\n")
            obj_file.write(f"# Source BIM Tool: {self.inspector.authoring_app}\n")
            obj_file.write(f"# Target Unit: METERS (Scale applied: {scale})\n")
            obj_file.write("# ------------------------------------------------------------\n\n")
            obj_file.write(f"mtllib {mtl_filename}\n\n")
            
            for idx, (cls_name, storey_name, elem) in enumerate(elements_to_export):
                elem_name = elem.Name or cls_name
                safe_name = sanitize_filename(f"{cls_name}_{elem_name}_{elem.GlobalId[:6]}")
                safe_storey = sanitize_filename(storey_name)
                
                if progress_callback:
                    progress_callback(idx + 1, total_elements, f"Tessellating: {cls_name} ({elem_name})")
                    
                # Create geometry shape
                try:
                    shape = ifcopenshell.geom.create_shape(geom_settings, elem)
                except Exception as e:
                    logger.debug(f"Could not tessellate element {elem.GlobalId}: {e}")
                    continue
                    
                verts = shape.geometry.verts
                faces = shape.geometry.faces
                if not verts or not faces:
                    continue
                    
                num_v = len(verts) // 3
                num_f = len(faces) // 3
                
                # Material selection
                mat_key = self._resolve_material(elem, cls_name)
                
                # Write Grouping & Object identifiers
                if group_by == "storey":
                    obj_file.write(f"g {safe_storey}_{cls_name}\n")
                elif group_by == "category":
                    obj_file.write(f"g {cls_name}\n")
                else: # both
                    obj_file.write(f"g {safe_storey}\n")
                    obj_file.write(f"g {cls_name}\n")
                    
                obj_file.write(f"o {safe_name}\n")
                obj_file.write(f"usemtl {mat_key}\n")
                
                # Write Vertices (applying scale to Meters)
                for v_i in range(0, len(verts), 3):
                    x = verts[v_i] * scale
                    y = verts[v_i + 1] * scale
                    z = verts[v_i + 2] * scale
                    obj_file.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
                    
                # Write Faces (1-based index)
                for f_i in range(0, len(faces), 3):
                    f1 = faces[f_i] + vertex_offset
                    f2 = faces[f_i + 1] + vertex_offset
                    f3 = faces[f_i + 2] + vertex_offset
                    obj_file.write(f"f {f1} {f2} {f3}\n")
                    
                vertex_offset += num_v
                total_vertices += num_v
                total_faces += num_f
                obj_file.write("\n")
                
        # Write MTL Library
        self._write_mtl_file(mtl_path)
        
        elapsed = time.time() - start_time
        file_size_kb = os.path.getsize(output_obj_path) / 1024.0
        
        logger.info(f"OBJ export finished in {elapsed:.2f}s: {total_vertices} verts, {total_faces} faces, {file_size_kb:.1f} KB")
        
        return {
            "obj_path": output_obj_path,
            "mtl_path": mtl_path,
            "total_vertices": total_vertices,
            "total_faces": total_faces,
            "file_size_kb": file_size_kb,
            "elapsed_seconds": elapsed,
        }

    def _resolve_material(self, elem: Any, cls_name: str) -> str:
        """Determine material definition and color for the element."""
        mat_def = DEFAULT_MATERIALS.get(cls_name, DEFAULT_MATERIALS["Default"])
        mat_name = mat_def["name"]
        
        # Check if element has custom surface colour in IFC
        custom_color = None
        try:
            for rel in getattr(elem, "HasAssociations", []):
                if rel.is_a("IfcRelAssociatesMaterial"):
                    # Material info exists
                    pass
        except Exception:
            pass
            
        if mat_name not in self.materials_written:
            self.materials_written[mat_name] = mat_def
            
        return mat_name

    def _write_mtl_file(self, mtl_path: str):
        """Write out the MTL file with realistic lighting reflectances."""
        with open(mtl_path, "w", encoding="utf-8") as mtl:
            mtl.write("# ------------------------------------------------------------\n")
            mtl.write("# DIALux evo Photometric Material Library\n")
            mtl.write("# Generated by DIALux IFC Bridge\n")
            mtl.write("# ------------------------------------------------------------\n\n")
            
            for mat_name, props in self.materials_written.items():
                kd = props.get("Kd", (0.7, 0.7, 0.7))
                ks = props.get("Ks", (0.1, 0.1, 0.1))
                d = props.get("d", 1.0)
                desc = props.get("desc", "")
                
                mtl.write(f"# {desc}\n")
                mtl.write(f"newmtl {mat_name}\n")
                mtl.write("Ka 0.2000 0.2000 0.2000\n")
                mtl.write(f"Kd {kd[0]:.4f} {kd[1]:.4f} {kd[2]:.4f}\n")
                mtl.write(f"Ks {ks[0]:.4f} {ks[1]:.4f} {ks[2]:.4f}\n")
                mtl.write(f"d {d:.2f}\n")
                mtl.write("illum 2\n")
                mtl.write("Ns 10.0\n\n")
