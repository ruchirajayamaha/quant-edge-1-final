"""Authoritative report build: figures, generated LaTeX, XeLaTeX compilation, checks, publish.

Usage:
    python scripts/build_reports.py            # full build, publish to FINAL_SUBMISSION/
    python scripts/build_reports.py --no-publish
    python scripts/build_reports.py --tex-only  # skip figure export

Requires a TeX distribution with xelatex and bibtex, the Libertinus fonts, and
requirements-render.txt. Set QE_TEX_BIN to the TeX bin folder if it is not on PATH.
The Streamlit app does not need any of this.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "report/latex"
BUILD = ROOT / "tmp/report_build"
PAGE_LIMITS = {"main": (7, 15), "tear_sheet": (1, 1), "recommendation": (1, 1), "human_review_pack": (2, 5)}
PUBLISHED = {
    "main": "FINAL_SUBMISSION/01_Investment_Memo.pdf",
    "tear_sheet": "FINAL_SUBMISSION/02_Executive_Tear_Sheet.pdf",
    "recommendation": "FINAL_SUBMISSION/supporting/Recommendation.pdf",
    "human_review_pack": "handoff/human_review_pack/human_review_pack.pdf",
}
FATAL_LOG = re.compile(r"^!|Missing character|There were undefined references|Citation .* undefined|Reference .* undefined|Label\(s\) may have changed")


def tex_environment() -> dict[str, str]:
    env = dict(os.environ)
    candidates = [env.get("QE_TEX_BIN"), r"D:\QuantEdgeTools\miktex\miktex\bin\x64"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            env["PATH"] = candidate + os.pathsep + env.get("PATH", "")
    if shutil.which("xelatex", path=env["PATH"]) is None:
        raise SystemExit("xelatex not found. Install a TeX distribution or set QE_TEX_BIN. See report/latex/README.md.")
    return env


def run(command: list[str], env: dict[str, str], cwd: Path = SOURCE) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def compile_document(name: str, env: dict[str, str]) -> Path:
    """Run XeLaTeX and BibTeX until references settle, failing on real errors."""
    xelatex = ["xelatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={BUILD}", f"{name}.tex"]
    first = run(xelatex, env)
    if first.returncode != 0:
        raise SystemExit(f"{name}: XeLaTeX failed\n{first.stdout[-1800:]}")
    if name == "main":
        bib_env = dict(env, BIBINPUTS=str(SOURCE) + os.pathsep, BSTINPUTS=str(SOURCE) + os.pathsep)
        bib = run(["bibtex", "main"], bib_env, cwd=BUILD)
        if bib.returncode != 0:
            raise SystemExit(f"bibtex failed\n{bib.stdout[-1500:]}")
    for _ in range(3):
        result = run(xelatex, env)
        if result.returncode != 0:
            raise SystemExit(f"{name}: XeLaTeX failed\n{result.stdout[-1800:]}")
        log = (BUILD / f"{name}.log").read_text(encoding="utf-8", errors="replace")
        if "Rerun to get" not in log and "Label(s) may have changed" not in log:
            break
    problems = [line for line in log.splitlines() if FATAL_LOG.search(line)]
    overfull = [line for line in log.splitlines() if line.startswith("Overfull \\hbox")
                and float(re.search(r"\(([\d.]+)pt too wide", line).group(1)) > 2.0]
    if problems or overfull:
        raise SystemExit(f"{name}: unresolved log problems\n" + "\n".join((problems + overfull)[:20]))
    return BUILD / f"{name}.pdf"


def page_count(path: Path) -> int:
    sys.path.insert(0, str(ROOT / "tmp/report_deps"))
    from pypdf import PdfReader

    return len(PdfReader(path).pages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-publish", action="store_true", help="Compile and check without replacing published PDFs.")
    parser.add_argument("--tex-only", action="store_true", help="Reuse existing figures.")
    args = parser.parse_args()

    env = tex_environment()
    BUILD.mkdir(parents=True, exist_ok=True)
    if not args.tex_only:
        subprocess.run([sys.executable, str(ROOT / "scripts/export_report_figures.py")], check=True, env=env)
    subprocess.run([sys.executable, str(ROOT / "scripts/generate_report_data.py")], check=True, env=env)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_human_review_pack.py")], check=True, env=env)

    built: dict[str, Path] = {}
    for name, (low, high) in PAGE_LIMITS.items():
        built[name] = compile_document(name, env)
        pages = page_count(built[name])
        if not low <= pages <= high:
            raise SystemExit(f"{name}: {pages} pages, expected {low}-{high}.")
        print(f"{name}: {pages} pages")

    if not args.no_publish:
        for name, target in PUBLISHED.items():
            (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built[name], ROOT / target)
        print("Published to FINAL_SUBMISSION/ and handoff/human_review_pack/")


if __name__ == "__main__":
    main()
