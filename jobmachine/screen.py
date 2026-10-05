#!/usr/bin/env python3
"""screen.py -> print screening signals for gate_passed/needs_judgment postings (non-HOLD)."""
import sqlite3,json,re,urllib.request,html,os,sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jobq import DB  # noqa: E402
c=sqlite3.connect(DB)
rows=c.execute("select key,title,location from postings where status in ('gate_passed','needs_judgment') and coalesce(reason,'') not like 'HOLD%'").fetchall()
cache={}
def get(u):
    if u not in cache:
        try: cache[u]=json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read())
        except Exception: cache[u]=None
    return cache[u]
for k,t,l in rows:
    src,slug,jid=k.split(':',2); body=''
    if src=='ashby':
        d=get(f'https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true')
        j=next((j for j in (d or {}).get('jobs',[]) if j['id']==jid),None)
        if j: body=(j.get('descriptionPlain') or '')+' COMP:'+str((j.get('compensation') or {}).get('compensationTierSummary'))+' WP:'+str(j.get('workplaceType'))
    elif src=='lever':
        d=get(f'https://api.lever.co/v0/postings/{slug}/{jid}')
        if d: body=(d.get('descriptionPlain') or '')+' '+' '.join(x.get('content','') for x in d.get('lists',[]))+' WP:'+str(d.get('workplaceType'))
    elif src=='gh':
        d=get(f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}')
        if d: body=re.sub('<[^>]+>',' ',html.unescape(d.get('content','')))
    body=re.sub(r'\s+',' ',body)
    yrs=sorted(set(m.group(0)[:70] for m in re.finditer(r'\d+\+?\s*(?:-|–|to)?\s*\d*\+?\s*years?[^.]{0,50}',body)))
    flags=[w for w in ['clearance','citizen','onsite','on-site','in-office','hybrid','travel','Python','TypeScript','SQL','Salesforce','license','bachelor','computer science','relocat','Spanish','Portuguese','quota'] if re.search(re.escape(w),body,re.I)]
    print(f"{k} | {t} | {l[:80]}\n   yrs={yrs[:4]} flags={flags} {re.findall(r'COMP:[^W]*',body)[:1]} {re.findall(r'WP:\S+',body)}")
