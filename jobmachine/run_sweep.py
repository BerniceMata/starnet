#!/usr/bin/env python3
"""run_sweep.py - time-boxed sweep for a StarNet Routine (or cron, or by hand).

A StarNet routine script gets 30 seconds by default (120 at most, via the routine's scriptTimeoutMs),
so this never tries to sweep everything at once. Each run takes the boards that were checked longest
ago, sweeps as many as fit in the budget, gates every new posting, and reports. Every 15 minutes at
the default budget, the whole board list rotates through in a few hours.

Output contract (StarNet pre-check script):
  - nothing new passed the gates -> last stdout line is {"wakeAgent":false}; the routine stays
    silent and spends no model call.
  - something new passed         -> a short report of the new roles; the routine wakes its agent
    with that report so it can screen them and tell you.

Usage: python3 run_sweep.py [--budget SECONDS] [--batch N]
       --budget must stay below the routine's script timeout (default 25 for StarNet's default 30s).
Env:   JOBMACHINE_BUDGET (default 25), JOBMACHINE_PROFILE, JOBMACHINE_DATA
"""
import concurrent.futures as cf
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ats_sweep  # noqa: E402
import jobq  # noqa: E402


def _arg(name, default):
    if name in sys.argv:
        return type(default)(sys.argv[sys.argv.index(name) + 1])
    return default


def kind_of(slug):
    if slug.startswith("ashby:"):
        return "ashby"
    if slug.startswith("lever:"):
        return "lever"
    return None if ":" in slug else "gh"


def fetch(slug):
    kind = kind_of(slug)
    if kind == "gh":
        _, code, data = jobq._sweep_board(slug)
        return kind, slug, code, data
    fn = ats_sweep.ashby if kind == "ashby" else ats_sweep.lever
    _, code, jobs = fn(slug.split(":", 1)[1])
    return kind, slug, code, jobs


def main():
    budget = _arg("--budget", int(os.environ.get("JOBMACHINE_BUDGET", "25")))
    batch = _arg("--batch", 48)
    # A batch can be held up by one slow board for the full request timeout, so keep the timeout short
    # and stop starting new batches once less than (timeout + a few seconds) of budget remains.
    jobq.HTTP_TIMEOUT = ats_sweep.HTTP_TIMEOUT = timeout = max(4, min(10, budget // 3))
    headroom = timeout + 4
    t0 = time.monotonic()
    started = jobq.NOW()
    c = jobq.conn()
    c.executescript(jobq.SCHEMA)
    ctx = jobq.sweep_context(c)
    applied, cooldown = ats_sweep.ledger_context(c)
    stats = dict(boards=0, live=0, discovered=0, evaluated=0, passed=0, judgment=0)

    # Stalest first; never-swept boards lead. Dead boards (live=0) are skipped.
    order = [r["slug"] for r in c.execute(
        "SELECT slug FROM boards WHERE live IS NULL OR live=1 ORDER BY last_swept IS NOT NULL, last_swept")]
    order = [s for s in order if kind_of(s)]
    i = 0
    with cf.ThreadPoolExecutor(16) as ex:
        while i < len(order) and time.monotonic() - t0 < budget - headroom:
            chunk = order[i:i + batch]
            i += len(chunk)
            for kind, slug, code, payload in ex.map(fetch, chunk):
                if kind == "gh":
                    jobq.ingest_greenhouse(c, slug, code, payload, ctx, stats)
                else:
                    ats_sweep.ingest(c, kind, slug.split(":", 1)[1], code, payload or [], applied, cooldown, stats)

    new = c.execute(
        """SELECT key, company, title, location, url, status, family FROM postings
           WHERE status IN ('gate_passed','needs_judgment') AND evaluated_at >= ?
           ORDER BY priority, family""", (started,)).fetchall()
    summary = {"boards_swept": stats["boards"], "boards_total": len(order), "new_postings": stats["discovered"],
               "new_passes": len(new), "seconds": round(time.monotonic() - t0, 1)}
    if not new:
        print(json.dumps(summary))
        print(json.dumps({"wakeAgent": False}))
        return
    print(f"Job machine: {len(new)} new role(s) passed the gates this sweep.")
    for r in new:
        tag = "needs judgment" if r["status"] == "needs_judgment" else r["family"]
        print(f"- {r['company']}: {r['title']} ({r['location']}) [{tag}] {r['url']}")
    print("Next: run `python3 screen.py` in this folder, then submit the survivors per README.md.")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
