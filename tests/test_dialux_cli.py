import subprocess
import os

dialux_exe = r"C:\Program Files\DIAL GmbH\DIALux\DIALux.exe"
print("DIALux exe exists:", os.path.exists(dialux_exe))
try:
    p = subprocess.run([dialux_exe, "--help"], capture_output=True, text=True, timeout=5)
    print("Returncode:", p.returncode)
    print("STDOUT:", p.stdout)
    print("STDERR:", p.stderr)
except Exception as e:
    print("Exception:", e)
