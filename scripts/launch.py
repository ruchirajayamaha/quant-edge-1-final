"""One-command local launch after documented installation; no market downloads."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'results/final/reference.json').exists():
    raise SystemExit('Missing final reference. Run python scripts/build_final_results.py first.')
raise SystemExit(subprocess.call([sys.executable,'-m','streamlit','run',str(ROOT/'app/Home.py'),
    '--browser.gatherUsageStats=false',*sys.argv[1:]],cwd=ROOT))
