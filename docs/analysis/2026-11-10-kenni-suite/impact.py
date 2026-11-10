import sqlite3,sys,collections,re,subprocess,statistics as st,xml.etree.ElementTree as ET
S=sys.argv[1]; root='/home/user/kenni'
db=sqlite3.connect(S+'/.coverage')
ctx={i:c.rsplit('|',1)[0] for i,c in db.execute('select id,context from context') if c}
files={i:p.replace(root+'/','') for i,p in db.execute('select id,path from file')}
ft=collections.defaultdict(set)
for fid,cid in db.execute('select distinct file_id,context_id from line_bits'):
    if cid in ctx: ft[files[fid]].add(ctx[cid])
tm={}
for c in ET.parse(S+'/junit3.xml').getroot().iter('testcase'):
    tm[c.get('classname').replace('.','/')+'.py::'+c.get('name')]=float(c.get('time') or 0)
def sec(t): return tm.get(re.sub(r'::[A-Z]\w*::','::',t),0.0)
alltests=set().union(*ft.values()); N=len(alltests); T=sum(sec(t) for t in alltests)
print('product files with coverage',len(ft),'tests',N,'time',round(T))
sh=sorted(len(v)/N for v in ft.values())
print('share of tests touching a file: median %.1f%%, p75 %.1f%%, p90 %.1f%%, max %.1f%%'%(100*sh[len(sh)//2],100*sh[len(sh)*3//4],100*sh[len(sh)*9//10],100*sh[-1]))
print('files touched by >50%% of tests: %d; by <5%%: %d of %d'%(sum(x>0.5 for x in sh),sum(x<0.05 for x in sh),len(sh)))
def git(*a): return subprocess.run(['git','-C',root,*a],capture_output=True,text=True,errors='replace').stdout
res=[]; nob=0; unk=0
for ln in git('log','--all','--merges','--format=%H %P %s').splitlines():
    m=re.match(r'^(\w+) (\w+) (\w+) train: merge (.+)$',ln)
    if not m: continue
    ch=[p for p in git('diff','--name-only','--no-renames',m[2],m[1]).splitlines()]
    src=[p for p in ch if p.startswith('backend/src/') and p.endswith('.py')]
    other_backend=[p for p in ch if p.startswith('backend/') and not p.startswith(('backend/src/','backend/tests/'))]
    tests_changed={p for p in ch if p.startswith('backend/tests/')}
    if not src and not tests_changed: nob+=1; continue
    sel=set()
    for p in src:
        if p in ft: sel|=ft[p]
        else: unk+=1
    # changed test files run themselves
    sel|={t for t in alltests if t.split('::')[0].replace('tests/','backend/tests/',1) in tests_changed}
    full = bool(other_backend) or any(p in('Makefile',) for p in ch)
    res.append((len(sel)/N, sum(sec(t) for t in sel)/T, len(src), full))
print('\ntrain merges analysed',len(res)+nob,'| without backend source or test change',nob,'| with',len(res),'| changed files unknown to coverage (new/deleted since)',unk)
a=sorted(r[1] for r in res)
print('share of backend suite TIME that touches the changed files: median %.0f%%, p25 %.0f%%, p75 %.0f%%, p90 %.0f%%'%(100*st.median(a),100*a[len(a)//4],100*a[len(a)*3//4],100*a[len(a)*9//10]))
print('merges needing <25%% of suite time: %d%%; <50%%: %d%%; >90%%: %d%%'%(100*sum(x<0.25 for x in a)//len(a),100*sum(x<0.5 for x in a)//len(a),100*sum(x>0.9 for x in a)//len(a)))
print('mean share %.0f%%'%(100*sum(a)/len(a)))
print('merges also touching backend config/lock (would force full run):',sum(r[3] for r in res))
top=sorted(ft.items(),key=lambda x:-len(x[1]))[:8]
print('\nfiles almost every test touches:')
for p,v in top: print('  %4.0f%% %s'%(100*len(v)/N,p))
