"""Build a source release without generated secrets, operational DBs, or dependency caches."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
output=root.parent/'SIM_Swap_Fraud_Detection_Platform.zip'
excluded={'.venv','node_modules','__pycache__','.pytest_cache','.ruff_cache','.git'}
files=[]
for path in sorted(root.rglob('*')):
    if not path.is_file():continue
    relative=path.relative_to(root)
    if any(part in excluded for part in relative.parts):continue
    if path.name=='.env' or path.suffix in {'.pyc','.db','.log'} or '.db-' in path.name:continue
    if path.name=='RELEASE_MANIFEST.json':continue
    files.append(path)
secrets=[]
if (root/'.env').exists():
    for line in (root/'.env').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if key in {'APP_SECRET','PSEUDONYM_KEY','POSTGRES_PASSWORD','REDIS_PASSWORD'}:secrets.append(value.encode())
for path in files:
    body=path.read_bytes()
    if any(value and value in body for value in secrets):raise RuntimeError(f'Generated secret found in {path.relative_to(root)}')
manifest={'release':'0.1.0','status':'reference demonstration; production gates not met',
          'files':[{'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in files],
          'excluded':'Local .env, operational DBs, dependency directories, caches and server logs',
          'checks':'Checked included bytes against this run\'s generated secrets; CI secret scanner still required'}
(root/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
files.append(root/'RELEASE_MANIFEST.json')
with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=9) as archive:
    for path in files:archive.write(path,'sim-swap-platform/'+path.relative_to(root).as_posix())
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert not any(name.endswith('/.env') or '/node_modules/' in name for name in archive.namelist())
print(json.dumps({'archive':str(output),'files':len(files),'bytes':output.stat().st_size,
                  'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))
