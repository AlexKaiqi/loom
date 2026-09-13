"""Finite ordinary-file/provider fixtures only; no Runtime/Harness implementation."""
from pathlib import Path
import json
PREFIX="BEGIN saved execution log\nrequested operation: inspect fixture values [2,3,5]\n"
SUFFIX="CHECK values_sum=10\nEND saved execution log\n"
def long_log():return (PREFIX+"progress data_雪\n"*4096+SUFFIX).encode()
def write_materials(workspace):
    for area in range(64):
        root=workspace/("catalog/area-%02d"%area);root.mkdir(parents=True,exist_ok=True)
        for n in range(8):
            selected=area==37 and n==4
            name="REQUESTED_COMPONENT.txt" if selected else "UNSELECTED_TREE_PATH_%02d_%02d.txt"%(area,n)
            body="REQUESTED_FILE_FRAGMENT: component Delta uses bounded ordinary files.\n" if selected else "UNSELECTED_FILE_BODY_%02d_%02d: unselected ordinary file contents.\n"%(area,n)
            (root/name).write_text(body)
    lines=["diff --git a/Delta.txt b/Delta.txt\n","--- a/Delta.txt\n","+++ b/Delta.txt\n"]
    for n in range(4096):lines.append("+REQUESTED_DIFF_FRAGMENT: Delta timeout changes from 3 to 5.\n" if n==2048 else "+UNSELECTED_DIFF_BODY_%04d: unchanged context outside requested material.\n"%n)
    (workspace/"changes.patch").write_text("".join(lines))
    return workspace/"catalog/area-37/REQUESTED_COMPONENT.txt",workspace/"changes.patch"
def retrieval_script(input_ref):
    # The provider fixture chooses an ordinary script. All selected content and
    # hashes come from actual files at runtime, never from expected assertions.
    body="""import pathlib,json,hashlib
root=pathlib.Path('.')
files=sorted(root.glob('catalog/area-*/REQUESTED_*.txt'))
if len(files)!=1:raise RuntimeError('expected a unique requested ordinary file')
selected=files[0];diff=root/'changes.patch'
def source(p):
 raw=p.read_bytes()
 return {'path':p.as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'input_ref':INPUT_REF}
print(json.dumps({'file_fragment':selected.read_text(),'diff_fragment':''.join(line for line in diff.read_text().splitlines(keepends=True) if line.startswith('+REQUESTED_DIFF_FRAGMENT:')),'sources':[source(selected),source(diff)]},ensure_ascii=False,sort_keys=True))
""".replace('INPUT_REF','json.loads('+repr(json.dumps(input_ref,ensure_ascii=False))+')')
    return "python3 - <<'PY'\n"+body+"PY\n"
