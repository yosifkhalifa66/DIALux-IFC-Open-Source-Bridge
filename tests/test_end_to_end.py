"""
End-to-End Test Suite for DIALux IFC Bridge
"""
import os
import sys

# Ensure src is discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ifc_parser import IfcModelInspector
from src.obj_exporter import DialuxObjExporter
from src.dxf_exporter import DialuxDxfExporter
from src.dialux_bridge import find_dialux_executable, copy_files_to_clipboard
from src.utils import get_default_export_dir

def run_tests():
    print("=" * 60)
    print("RUNNING DIALUX IFC BRIDGE PIPELINE TESTS")
    print("=" * 60)
    
    sample_ifc = os.path.join(os.path.dirname(__file__), "sample_office.ifc")
    assert os.path.exists(sample_ifc), f"Sample IFC not found: {sample_ifc}"
    
    # 1. Test Model Inspector
    print("\n[1/5] Testing IFC Inspector...")
    inspector = IfcModelInspector(sample_ifc)
    assert inspector.load() is True, "Failed to load sample IFC"
    summary = inspector.get_summary()
    print(f"  Project: {summary['project_name']}")
    print(f"  Schema: {summary['schema']}")
    print(f"  Length Unit: {summary['detected_unit']} (Scale: {summary['unit_scale_to_meters']})")
    print(f"  Total Elements: {summary['total_elements']}")
    print(f"  Storeys: {[s['name'] for s in summary['storeys']]}")
    print(f"  Categories: {summary['category_counts']}")
    assert summary["total_elements"] > 0, "No elements found in sample IFC"
    
    # 2. Test OBJ Exporter
    print("\n[2/5] Testing Wavefront OBJ & MTL Exporter...")
    obj_out = os.path.join(get_default_export_dir(), "test_export", "sample_office.obj")
    exporter = DialuxObjExporter(inspector)
    obj_result = exporter.export(
        output_obj_path=obj_out,
        scale_factor=inspector.unit_scale_to_meters,
        group_by="storey"
    )
    print(f"  OBJ Path: {obj_result['obj_path']} ({obj_result['file_size_kb']:.2f} KB)")
    print(f"  MTL Path: {obj_result['mtl_path']}")
    print(f"  Vertices: {obj_result['total_vertices']}, Triangles: {obj_result['total_faces']}")
    assert os.path.exists(obj_result["obj_path"]), "OBJ file was not created"
    assert os.path.exists(obj_result["mtl_path"]), "MTL file was not created"
    assert obj_result["total_vertices"] > 0, "Zero vertices generated"
    assert obj_result["total_faces"] > 0, "Zero faces generated"
    
    # 3. Test DXF Exporter
    print("\n[3/5] Testing 3D DXF CAD Exporter...")
    dxf_out = os.path.join(get_default_export_dir(), "test_export", "sample_office_3D.dxf")
    dxf_exporter = DialuxDxfExporter(inspector)
    dxf_result = dxf_exporter.export(output_dxf_path=dxf_out)
    print(f"  DXF Path: {dxf_result['dxf_path']}")
    print(f"  Faces: {dxf_result['total_faces']}")
    assert os.path.exists(dxf_result["dxf_path"]), "DXF file was not created"
    assert dxf_result["total_faces"] > 0, "Zero DXF faces generated"
    
    # 4. Test Clipboard CF_HDROP Transfer
    print("\n[4/5] Testing Windows CF_HDROP Clipboard Integration...")
    clipboard_ok = copy_files_to_clipboard([obj_result["obj_path"], obj_result["mtl_path"]])
    print(f"  Clipboard copy status: {clipboard_ok}")
    assert clipboard_ok is True, "CF_HDROP clipboard copy failed"
    
    # 5. Test DIALux Executable Detection
    print("\n[5/5] Testing DIALux evo Installation Detection...")
    dialux_exe = find_dialux_executable()
    print(f"  Detected DIALux exe: {dialux_exe}")
    assert dialux_exe is not None, "DIALux executable could not be detected on the system"
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! [OK]")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
