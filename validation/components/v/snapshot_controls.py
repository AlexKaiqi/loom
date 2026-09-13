"""Independent source binding controls; no candidate V implementation."""
from pathlib import Path
import hashlib,importlib,json,os,py_compile,sys
from source_snapshot import capture,load,unchanged
R=Path(__file__).resolve().parents[3];out=Path(__file__).parent/'evidence'/sys.argv[1];out.mkdir(parents=True,exist_ok=False);source=out/'fixture-source';package=source/'snapshot_fixture';package.mkdir(parents=True)
(package/'__init__.py').write_text('from .helper import VALUE\n');helper=package/'helper.py';helper.write_text('VALUE = 9\n');py_compile.compile(str(helper),doraise=True);st=helper.stat();helper.write_text('VALUE = 1\n');os.utime(helper,ns=(st.st_atime_ns,st.st_mtime_ns))
# Stale timestamp/size-valid pyc deliberately carries 9 while original source is 1.
record=capture('snapshot_fixture',[source],out/'executed-source');mod=load(record);rows=[]
def check(name,condition):rows.append({'id':name,'passed':condition})
check('full-package-has-helper',len(record['original'])==2);check('copied-package-not-old-pyc',mod.VALUE==1);check('unchanged-original-and-executed',unchanged(record));check('no-pyc-copied',not list((out/'executed-source').rglob('*.pyc')))
helper.write_text('VALUE = 2\n');check('original-helper-change-rejected',not unchanged(record));helper.write_text('VALUE = 1\n');check('original-restored',unchanged(record))
copied=out/'executed-source/snapshot_fixture/helper.py';copied.write_text('VALUE = 3\n');check('executed-helper-change-rejected',not unchanged(record));copied.write_text('VALUE = 1\n');check('executed-restored',unchanged(record))
r={'scope':'V runner source closure controls only','records':rows,'captured':record,'pass':all(x['passed'] for x in rows),'source_sha256':hashlib.sha256(Path(__file__).with_name('source_snapshot.py').read_bytes()).hexdigest()};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':r['pass'],'checks':len(rows)}));sys.exit(0 if r['pass'] else 1)
