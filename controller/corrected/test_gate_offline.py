"""Execute the actual runner's gate block with temporary synthetic records only."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile

source = Path(__file__).with_name('qwen_batch.py')
tree = ast.parse(source.read_text())
main = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main')
start = next(i for i,n in enumerate(main.body) if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='gate' for t in n.targets))
end = next(i for i,n in enumerate(main.body) if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='conf' for t in n.targets))
block = compile(ast.Module(body=main.body[start:end],type_ignores=[]),str(source),'exec')
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)/'runs'/'batch-1';root.mkdir(parents=True)
    runner=Path(tmp)/'qwen_batch.py';runner.write_bytes(source.read_bytes())
    (root/'config.json').write_text('{}')
    gate={'approved':True,'preflight_pass':True,'sha256':{'qwen_batch.py':hashlib.sha256(runner.read_bytes()).hexdigest(),'config.json':hashlib.sha256((root/'config.json').read_bytes()).hexdigest()}}
    def execute():
        (root/'execution-gate.json').write_text(json.dumps(gate))
        exec(block,{'ROOT':root,'hashlib':hashlib,'load':lambda p:json.loads(p.read_text())})
    execute()
    gate['approved']=False
    try:execute()
    except AssertionError:pass
    else:raise AssertionError('unapproved gate accepted')
    gate['approved']=True
    (root/'config.json').write_text('{"tampered":true}')
    try:execute()
    except AssertionError:pass
    else:raise AssertionError('changed config accepted')
print('PASS: actual runner gate accepts matching temporary records and rejects missing approval/tampered hash; no experiment executed')
