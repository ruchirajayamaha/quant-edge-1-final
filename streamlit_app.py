"""Community Cloud entrypoint for the existing src-layout application.

Cloud installs requirements.txt; expose the local analytical package without
requiring a separate editable-install command or modifying frozen requirements.
The local launcher and this entrypoint both execute app/Home.py.
"""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
runpy.run_path(str(ROOT / "app" / "Home.py"), run_name="__main__")
