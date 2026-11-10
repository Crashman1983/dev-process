import sqlite3,sys,collections,re,json,xml.etree.ElementTree as ET
from coverage.numbits import numbits_to_nums
S=sys.argv[1]
db=sqlite3.connect(S+'/.coverage')
ctx={i:c for i,c in db.execute('select id,context from context')}
files={i:p for i,p in db.execute('select id,path from file')}
def test_of(c): return c.rsplit('|',1)[0] if c else ''
tests=sorted({test_of(c) for c in ctx.values() if c})
tid={t:i for i,t in enumerate(tests)}
print('contexts',len(ctx),'tests',len(tests),'files',len(files))
# pass 1: per line -> number of distinct tests (cap at 3) ; store first test id
cnt={}; first={}
per_test_lines=collections.Counter()
rows=0
for fid,cid,nb in db.execute('select file_id,context_id,numbits from line_bits'):
    c=ctx.get(cid)
    if not c: continue
    t=tid[test_of(c)]; base=fid<<20
    for ln in numbits_to_nums(nb):
        k=base|ln
        f=first.get(k)
        if f is None: first[k]=t; cnt[k]=1
        elif f!=t and cnt[k]<3:
            # distinct-ish count: only exact for 1 vs >1 when same test repeats phases
            if cnt[k]==1: cnt[k]=2
        rows+=1
print('line records',rows,'distinct lines covered',len(cnt))
uniq=collections.Counter(first[k] for k,v in cnt.items() if v==1)
total_lines=len(cnt); once=sum(1 for v in cnt.values() if v==1)
print('lines covered by exactly one test:',once,f'({once*100//total_lines}%)')
# times
tm={}
for c in ET.parse(S+'/junit3.xml').getroot().iter('testcase'):
    tm[c.get('classname').replace('.','/')+'.py::'+c.get('name')]=float(c.get('time') or 0)
def norm(t): 
    # coverage context: tests/a/b.py::test_x[param]  (may include class)
    return re.sub(r'::[A-Z]\w*::','::',t)
T=collections.Counter(); N=collections.Counter(); Z=collections.Counter(); ZT=collections.Counter(); TT=collections.Counter()
zero=[]
for t,i in tid.items():
    top='/'.join(t.split('/')[1:3]) if t.startswith('tests/') else 'other'
    top=top.split('::')[0]
    sec=tm.get(norm(t),0.0)
    N[top]+=1; TT[top]+=sec
    if uniq.get(i,0)==0: Z[top]+=1; ZT[top]+=sec; zero.append((sec,t))
n=len(tid); z=sum(Z.values()); tt=sum(TT.values()); zt=sum(ZT.values())
print(f'\ntests with coverage context: {n}; with NO line that only they cover: {z} ({z*100//n}%); their time {zt:.0f}s of {tt:.0f}s ({zt*100//max(1,tt):.0f}%)')
print('area                          tests  zero-unique  share  time_zero_s')
for k,v in N.most_common(18): print(f"  {k:28} {v:5} {Z[k]:6} {Z[k]*100//v:5}% {ZT[k]:8.0f}")
print('\nslowest tests without a unique line:')
for sec,t in sorted(zero,reverse=True)[:12]: print(f"  {sec:6.1f}s {t[:120]}")
# tests not in coverage at all (touch no product code)
alltests=set(tm); covered={norm(t) for t in tid}
nocov=[t for t in alltests if t not in covered]
print('\njunit tests',len(alltests),'| tests that executed no product line (no context):',len(nocov),f'time {sum(tm[t] for t in nocov):.0f}s')
print(' by dir:',collections.Counter(t.split('/')[1] for t in nocov).most_common(8))
