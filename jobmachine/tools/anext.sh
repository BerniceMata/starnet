#!/bin/bash
# anext.sh N -> next N Ashby keys with clean plans; writes scratchpad/ak_<n>.js (fill JS) and prints key/title/url/resume
mkdir -p ${JM_SCRATCH:-/tmp/jm}
cd /home/claude/jm/jobmachine; P=${JM_SCRATCH:-/tmp/jm}
rm -f $P/ak_*.js; n=0
for k in $(python3 -c "
import json,sqlite3;c=sqlite3.connect('data/jobs.db')
st={r[0]:r[1] for r in c.execute('select key,status from postings')}
print(' '.join(x for x in json.load(open('data/queue_ashby.json')) if st.get(x)=='gate_passed'))"); do
  out=$(timeout 40 python3 ashcall.py $k 2>$P/aerr.txt) || { echo "ERR $k"; continue; }
  if ! grep -q 'UNKNOWN: \[\] | BLOCK: \[\]' $P/aerr.txt; then echo "HOLD $k $(cut -c1-300 $P/aerr.txt | sed 's/.*UNKNOWN/UNKNOWN/')"; continue; fi
  if echo "$out" | grep -qiE '"title": "[^"]*(sponsor|visa)[^"]*", "type": "[^"]*", "answer": "Yes"'; then echo "STOP sponsor-yes $k"; continue; fi
  echo "$out" > $P/ak_$n.js
  echo "OK $n $k | $(python3 -c "import sqlite3;c=sqlite3.connect('data/jobs.db');print(' | '.join(map(str,c.execute('select company,title,location from postings where key=?',('$k',)).fetchone())))") | $(python3 resume_for.py $k)"
  n=$((n+1)); [ $n -ge ${1:-6} ] && break
done
