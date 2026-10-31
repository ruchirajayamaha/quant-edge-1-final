"""Package reviewed documents, evidence and actual headline tables; no credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1];SUB=ROOT/'submission'

def main():
    shutil.copy2(ROOT/'AI_DISCLOSURE.md',SUB/'AI_DISCLOSURE.md')
    shutil.copy2(ROOT/'README.md',SUB/'REPOSITORY_README.md')
    for name in ['publication.json','clean_install.json','verification.json']:
        path=ROOT/'audit/step9_review'/name
        if path.exists():shutil.copy2(path,SUB/name)
    tables=SUB/'tables';tables.mkdir(exist_ok=True)
    for name in ['period_kpis.csv','risk_table.csv','coverage_summary.csv','stress_results.csv','evt_diagnostics.csv','reference.json']:
        shutil.copy2(ROOT/'results/final'/name,tables/name)
    files=sorted(p for p in SUB.rglob('*') if p.is_file() and p.name!='artifact_manifest.json')
    ref=json.loads((ROOT/'results/final/reference.json').read_text())
    manifest={'bundle_id':ref['metadata']['bundle_id'],'dataset_id':ref['metadata']['dataset_id'],
       'human_validation':'PENDING','file_sha256':{p.relative_to(SUB).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (SUB/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    output=ROOT/'QuantEdge_Final_Submission.zip'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SUB.rglob('*')):
            if path.is_file():archive.write(path,arcname='QuantEdge_Final_Submission/'+path.relative_to(SUB).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all('..' not in Path(n).parts and not Path(n).is_absolute() for n in archive.namelist())
    print(output.name,output.stat().st_size,'bytes',hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':main()
