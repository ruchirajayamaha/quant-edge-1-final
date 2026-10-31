"""Render PDF pages to PNG for visual review. Requires pypdfium2 (requirements-render.txt).

Usage: python scripts/render_pdf_pages.py <pdf> <output_dir> [scale] [first_page] [last_page]
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tmp/report_deps"))

import pypdfium2 as pdfium


def main() -> None:
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.4
    document = pdfium.PdfDocument(str(source))
    first = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    last = int(sys.argv[5]) if len(sys.argv) > 5 else len(document)
    output.mkdir(parents=True, exist_ok=True)
    for number in range(first, last + 1):
        image = document[number - 1].render(scale=scale).to_pil()
        image.save(output / f"{source.stem}-{number:02d}.png")
    print(source.name, len(document), "pages")


if __name__ == "__main__":
    main()
