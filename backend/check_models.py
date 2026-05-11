import os, re

model_dir = 'models'
model_classes = {}

for fname in sorted(os.listdir(model_dir)):
    if not fname.endswith('.py') or fname == '__init__.py':
        continue
    filepath = os.path.join(model_dir, fname)
    with open(filepath) as f:
        content = f.read()
    
    for match in re.finditer(r'class (\w+)\((?:Base|.*Base.*)\):', content):
        classname = match.group(1)
        tbl_match = re.search(r'__tablename__\s*=\s*["\x27](\w+)["\x27]', content[match.start():match.start()+500])
        tablename = tbl_match.group(1) if tbl_match else '???'
        model_classes[classname] = (fname, tablename)

with open(os.path.join(model_dir, '__init__.py')) as f:
    init_content = f.read()

missing = []
for classname, (fname, tablename) in sorted(model_classes.items()):
    if classname not in init_content:
        missing.append((classname, tablename, fname))

with open('/tmp/audit_result.txt', 'w') as f:
    f.write(f'Total models: {len(model_classes)}\n')
    f.write(f'Missing: {len(missing)}\n\n')
    for cls, tbl, fn in missing:
        f.write(f'{cls} | table={tbl} | file={fn}\n')
