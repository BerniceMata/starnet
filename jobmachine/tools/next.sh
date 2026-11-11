#!/bin/bash
# next.sh N -> next N queue keys that have no unknowns/blockers, with packets saved to scratchpad/pk_<n>.txt
mkdir -p ${JM_SCRATCH:-/tmp/jm}
cd /home/claude/jm/jobmachine; P=${JM_SCRATCH:-/tmp/jm}
n=0
for k in $(python3 -c "
import json,sqlite3;c=sqlite3.connect('data/jobs.db')
q=json.load(open('data/queue_gh.json'))
st={r[0]:r[1] for r in c.execute('select key,status from postings')}
print(' '.join(x for x in q if st.get(x)=='gate_passed'))"); do
  u=$(timeout 40 python3 answers.py $k 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['unknown'])+len(d['blockers']))" 2>/dev/null)
  if [ "$u" != "0" ]; then python3 jobq.py mark $k needs_judgment "unknown required question" >/dev/null 2>&1; echo "HOLD $k"; continue; fi
  $P/pj.sh $k > $P/pk_$n.txt 2>&1 || { echo "ERR $k"; continue; }
  grep -q '^SKIP' $P/pk_$n.txt && { echo "SKIP $k"; continue; }
  echo "OK $n $k"; n=$((n+1)); [ $n -ge ${1:-5} ] && break
done
