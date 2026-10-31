"""Refresh FINAL_SUBMISSION, write its checksums, and archive it as the single ZIP."""
import hashlib
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1];FINAL=ROOT/'FINAL_SUBMISSION'
INTERMEDIATES=('*.aux','*.log','*.out','*.toc','*.bbl','*.blg','*.xdv','*.fls','*.fdb_latexmk')
ARCHIVE='QuantEdge_Final_Submission.zip'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    shutil.copy2(ROOT/'AI_DISCLOSURE.md',FINAL/'AI_DISCLOSURE.md')
    source=FINAL/'latex_source'
    if source.exists():shutil.rmtree(source)
    shutil.copytree(ROOT/'report/latex',source,ignore=shutil.ignore_patterns(*INTERMEDIATES))
    sums=FINAL/'SHA256SUMS.txt'
    files=sorted(p for p in FINAL.rglob('*') if p.is_file() and p!=sums)
    expected={p.relative_to(FINAL).as_posix():sha(p.read_bytes()) for p in files}
    sums.write_bytes(''.join(f'{digest}  {name}\n' for name,digest in expected.items()).encode('utf-8'))
    output=ROOT/ARCHIVE
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(FINAL.rglob('*')):
            if path.is_file():archive.write(path,arcname='FINAL_SUBMISSION/'+path.relative_to(FINAL).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all('..' not in Path(n).parts and not Path(n).is_absolute() for n in archive.namelist())
        assert set(archive.namelist())=={'FINAL_SUBMISSION/SHA256SUMS.txt'}|{'FINAL_SUBMISSION/'+n for n in expected}
        for name,digest in expected.items():
            assert sha(archive.read('FINAL_SUBMISSION/'+name))==digest,name
    print(output.name,output.stat().st_size,'bytes',sha(output.read_bytes()))

if __name__=='__main__':main()
