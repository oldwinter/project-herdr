from pathlib import Path
import subprocess, os, json, hashlib, socket, re, shlex, shutil, sys, datetime
BASE=Path('/tmp/project-herdr-selftest-dfrb_g65')
ROOT=BASE/'coordinator'
PRODUCT=BASE/'product-fixture'
OUT=Path('/home/cdd/project-herdr/context/internal/d-20260913-pr-5-a-d-f-cli')
OUT.mkdir(parents=True, exist_ok=True)
LOG=OUT/'commands.jsonl'
assertions=[]
env=os.environ.copy()
env.pop('HERDR_ENV',None)
env.pop('PROJECT_HERDR_DEVICE',None)
for key in list(env):
    if key.startswith('PROJECT_HERDR_PATH_'):
        env.pop(key)
env['PYTHONDONTWRITEBYTECODE']='1'
sequence=0

def log(row):
    global sequence
    sequence+=1
    row={'seq':sequence, 'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(), **row}
    with LOG.open('a') as f: f.write(json.dumps(row,ensure_ascii=False)+'\n')
    return sequence

def run(argv, cwd=ROOT, overrides=None, expected=0):
    e=env.copy()
    if overrides:
        for k,v in overrides.items():
            if v is None: e.pop(k,None)
            else: e[k]=v
    p=subprocess.run(argv,cwd=cwd,env=e,text=True,capture_output=True,timeout=90)
    n=log({'type':'command','command':shlex.join(argv),'argv':argv,'cwd':str(cwd),'env_overrides':overrides or {},'HERDR_ENV':'unset','exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    if expected is not None: check(f'command {n} exits {expected}',p.returncode==expected, f'actual {p.returncode}')
    return p

def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text)
    log({'type':'write_fixture','path':str(path),'content':text})

def check(name,ok,detail=''):
    row={'name':name,'passed':bool(ok),'detail':detail}
    assertions.append(row)
    log({'type':'assertion',**row})
    if not ok: print('FAIL', name, detail,flush=True)

def read(path):
    text=path.read_text()
    log({'type':'read_artifact','path':str(path),'content':text})
    return text

def snap(label):
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for area in ['control/dispatches','control/receipts'] for p in sorted((ROOT/area).rglob('*')) if p.is_file()}
    for name in ['control/notes.md','control/archived.md']:
        p=ROOT/name
        if p.exists(): files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(OUT/f'{label}.json',json.dumps(files,indent=2)+'\n')
    return files

def create(objective,harness='codex',json_mode=True,extra=None):
    p=run(['just','dispatch','create','--workspace','skills','--objective',objective,'--harness',harness,'--accept','just test','--ready']+(['--json'] if json_mode else [])+(extra or []))
    if json_mode: return json.loads(p.stdout)['id']
    return p.stdout.split()[0]

def receipt(d,verdict,summary,evidence=None):
    return run(['just','receipt','record','--dispatch',d,'--verdict',verdict,'--summary',summary]+(['--evidence',evidence] if evidence else []))

print('A: cold start',flush=True)
run(['git','rev-parse','HEAD'])
run(['python3','--version'])
p=run(['just','check']); check('A 37 tests pass','Ran 37 tests' in p.stderr and '\nOK\n' in p.stderr,p.stderr[-250:])
p=run(['just','start']);check('A start final line notes',p.stdout.strip().splitlines()[-1].strip()=='project-herdr notes',p.stdout)
p=run(['just','doctor']);check('A six harnesses',bool(re.search(r'harnesses\s+claude codex droid grok hermes pi',p.stdout)))
run(['just','workspaces']);run(['just','status']);run(['just','inbox']);run(['just','notes'])
p=run(['just','context']);check('A context folders exist',all((ROOT/'context'/x).is_dir() and f'context/{x}' in p.stdout for x in ['docs','internal','media']))
p=run(['just','--json','doctor'],expected=None);check('Guide JSON invocation rejects --json before recipe',p.returncode!=0,p.stderr)
p=run(['just','doctor','--json']);check('Correct JSON invocation',json.loads(p.stdout)['ok'])
print('B: workspace registration',flush=True)
PRODUCT.mkdir()
run(['git','init','-b','main'],cwd=PRODUCT)
run(['git','remote','add','origin','git@github.com:oldwinter/skills.git'],cwd=PRODUCT)
write(PRODUCT/'README.md','# Skills QA fixture\n')
write(PRODUCT/'justfile','test:\n    @python3 -c "from pathlib import Path; assert Path(\'README.md\').read_text().strip(); print(\'fixture test passed\')"\n')
run(['git','add','README.md','justfile'],cwd=PRODUCT)
run(['git','-c','user.name=Coordinator QA','-c','user.email=qa@example.invalid','commit','-m','Initialize isolated QA fixture'],cwd=PRODUCT)
write(ROOT/'control/workspaces.local.toml','[[workspaces]]\nid = "skills"\nname = "Skills"\nkind = "product"\nremote = "git@github.com:oldwinter/skills.git"\ndefault_harness = "codex"\nentry = "just test"\n')
env['PROJECT_HERDR_PATH_SKILLS']=str(PRODUCT)
run(['just','workspaces'])
p=run(['just','status','--json']); data=json.loads(p.stdout); row=next(x for x in data if x['id']=='skills');check('B env path and clean git',row.get('path')==str(PRODUCT) and row.get('git')=='ok' and not row.get('dirty'),str(row))
write(ROOT/f'control/overlays/{socket.gethostname().lower()}/paths.toml',f'device = "{socket.gethostname().lower()}"\n[paths]\nskills = "{PRODUCT}"\n')
env.pop('PROJECT_HERDR_PATH_SKILLS')
p=run(['just','status','--json']);row=next(x for x in json.loads(p.stdout) if x['id']=='skills');check('B hostname overlay path and git',row.get('path')==str(PRODUCT) and row.get('git')=='ok',str(row))
print('C: manual worker loop and archive',flush=True)
d=create('在 README 顶部加一行一句话简介',json_mode=False)
notes=read(ROOT/'control/notes.md');check('C create immediately updates notes',f'[{d}]' in notes and 'ready, waiting for a worker' in notes)
prompt=read(ROOT/f'control/runtime/{d}/prompt.md');check('C prompt Output evidence and attach instructions',all(x in prompt for x in ['## Output',f'context/internal/{d}/report.md','dispatch attach','--pr']))
run(['just','notes'])
# Contract above authorizes this isolated worker action; execute in product cwd.
run(['python3','-c',"from pathlib import Path; p=Path('README.md'); p.write_text('A temporary product repository for coordinator self-testing.\\n'+p.read_text())"],cwd=PRODUCT)
run(['just','test'],cwd=PRODUCT)
run(['git','diff','--','README.md'],cwd=PRODUCT)
p=run(['just','status','--json']); row=next(x for x in json.loads(p.stdout) if x['id']=='skills');check('B/C dirty reflects worker diff',bool(row.get('dirty')),str(row))
evidence=f'context/internal/{d}/report.md';write(ROOT/evidence,'改了 README 第一行；just test 通过（隔离 fixture）\n')
receipt(d,'needs_review','README 加了简介，等你看一眼',evidence)
notes=read(ROOT/'control/notes.md');check('C receipt immediately updates notes','— README 加了简介，等你看一眼' in notes)
p=run(['just','inbox']);check('C review inbox','review' in p.stdout and d in p.stdout and 'needs_review' in p.stdout)
run(['just','notes'])
receipt(d,'passed','合入')
notes=read(ROOT/'control/notes.md');check('C passed checkbox',f'- [x] [{d}]' in notes)
p=run(['just','inbox']);check('C inbox empty after passed',p.stdout.strip()=='Inbox empty.',p.stdout)
run(['just','notes'])
completed=[d]
for i in range(4):
    x=create(f'archive fixture {i}')
    receipt(x,'passed',f'Archive completion {i}')
    completed.append(x)
notes=read(ROOT/'control/notes.md');archive=read(ROOT/'control/archived.md')
check('C latest three completed notes only',notes.count('- [x]')==3,str(notes.count('- [x]')))
check('C remaining completed archived',all(f'[{x}]' in notes or f'[{x}]' in archive for x in completed) and archive.count('- [x]')==2)
print('D: real GitHub read-only PR state',flush=True)
dmerge=create('real merged PR sync QA');dopen=create('real open PR sync QA')
for x,url in [(dmerge,'https://github.com/oldwinter/project-herdr/pull/4'),(dopen,'https://github.com/oldwinter/project-herdr/pull/5')]:
    run(['just','dispatch','attach',x,'--pr',url]);notes=read(ROOT/'control/notes.md');check(f'D attach immediately links {x}',f'[PR]({url})' in notes)
run(['just','notes'])
before=snap('real-dry-run-before');p=run(['just','sync','--dry-run','--json']);after=snap('real-dry-run-after');check('D real dry-run writes no files',before==after)
rows=json.loads(p.stdout);check('D actual PR4 merged -> done dry-run',any(x['dispatch_id']==dmerge and x['lifecycle']=='merged' and x['action']=='done' for x in rows),p.stdout)
check('D actual PR5 open',any(x['dispatch_id']==dopen and x['lifecycle']=='open' for x in rows),p.stdout)
p=run(['just','sync','--json']);notes=read(ROOT/'control/notes.md');check('D sync updates notes immediately','PR merged' in notes)
p=run(['just','dispatch','show',dmerge,'--json']);check('D actual merged contract done',json.loads(p.stdout)['status']=='done')
print('D: explicit local gh failure/CI simulations',flush=True)
stub=BASE/'gh-stub';stub.mkdir()
write(stub/'gh','#!/usr/bin/python3\nimport os,json,sys\nmode=os.environ["QA_GH_MODE"]\nif mode=="unauthenticated":\n print("To get started with GitHub CLI, please run: gh auth login", file=sys.stderr);sys.exit(4)\nprint(json.dumps({"state":"OPEN","mergedAt":None,"statusCheckRollup":[{"conclusion":"FAILURE","status":"COMPLETED"}]}))\n')
(stub/'gh').chmod(0o755)
fail_env={'PATH':str(stub)+':'+env['PATH'],'QA_GH_MODE':'unauthenticated'}
before=snap('unauthenticated-before');p=run(['just','sync','--json'],overrides=fail_env);after=snap('unauthenticated-after');rows=json.loads(p.stdout)
check('D simulated unauth probe_failed login hint',all(x['action']=='probe_failed' and 'gh auth login' in x['detail'] for x in rows),p.stdout)
check('D simulated unauth contracts receipts unchanged',before==after)
# Empty PATH fixture supplies only shell, just and python; gh cannot resolve.
missing=BASE/'without-gh';missing.mkdir()
for name in ['sh','just','python3']:(missing/name).symlink_to(shutil.which(name))
before=snap('missing-gh-before');p=run([str(missing/'just'),'sync','--json'],overrides={'PATH':str(missing)},expected=None);after=snap('missing-gh-after')
check('D gh missing fails closed',p.returncode!=0 and 'gh is not on PATH' in p.stderr and before==after,p.stderr)
red_env={'PATH':str(stub)+':'+env['PATH'],'QA_GH_MODE':'red'}
before=snap('ci-red-dry-run-before');p=run(['just','sync','--dry-run','--json'],overrides=red_env);after=snap('ci-red-dry-run-after');check('D simulated CI red dry-run immutable',before==after)
check('D simulated CI red dry-run needs_review',any(x['checks']=='failing' and x['action']=='needs_review' for x in json.loads(p.stdout)),p.stdout)
p=run(['just','sync','--json'],overrides=red_env);notes=read(ROOT/'control/notes.md');check('D simulated CI-red sync immediately notes','CI failing on PR' in notes)
p=run(['just','dispatch','show',dopen,'--json']);check('D simulated CI-red contract needs_review',json.loads(p.stdout)['status']=='needs_review')
p=run(['just','inbox','--json']);check('D simulated CI-red inbox review',any(x['dispatch_id']==dopen for x in json.loads(p.stdout)),p.stdout)
print('E negative only; interchangeable ready prompts',flush=True)
pre=set((ROOT/'control/dispatches').glob('*.toml'))
p=run(['just','dispatch','create','--workspace','skills','--objective','negative enqueue outside Herdr','--enqueue','--json'],expected=None)
post=set((ROOT/'control/dispatches').glob('*.toml'));new=list(post-pre)
check('E negative enqueue not_in_herdr_pane',p.returncode!=0 and 'not_in_herdr_pane' in p.stderr,p.stderr)
check('E negative enqueue retains ready contract',len(new)==1 and 'status = "ready"' in read(new[0]))
normalized=[]
for harness in ['pi','codex','claude']:
    x=create('Compare interchangeable harness prompt',harness)
    text=read(ROOT/f'control/runtime/{x}/prompt.md')
    normalized.append(text.replace(x,'DISPATCH_ID'))
    p=run(['just','dispatch','show',x,'--json']);check(f'harness {harness} retained in contract',json.loads(p.stdout)['harness']==harness)
check('Harness prompts identical after ID normalization',len(set(normalized))==1)
print('F: lesson and final scope',flush=True)
run(['just','lesson','add','skills 仓 just test 前要先 just seed','--workspace','skills'])
text=read(ROOT/'context/docs/lessons.md');check('F lesson persisted','skills 仓 just test 前要先 just seed' in text and 'skills' in text)
p=run(['git','status','--porcelain','--untracked-files=all']);write(OUT/'coordinator-git-status.txt',p.stdout)
paths=[line[3:] for line in p.stdout.splitlines()]
check('Coordinator only changes control and context',all(x.startswith(('control/','context/')) for x in paths),str(paths))
p=run(['git','diff','--name-only'],cwd=PRODUCT);check('Worker diff only product README',p.stdout.strip()=='README.md',p.stdout)
run(['git','diff','--exit-code','--','src','tests','docs','justfile','AGENTS.md'])
write(OUT/'assertions.json',json.dumps(assertions,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'assertions':len(assertions),'failures':[x for x in assertions if not x['passed']],'log':str(LOG)},ensure_ascii=False,indent=2),flush=True)
