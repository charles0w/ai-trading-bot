"""
Smoke-test the eval reporting pipe end to end.

Posts a few sample quality scores for the `finance` agent to the live
ceos-enterprise dashboard, so you can confirm report -> registry -> eval_runs
-> Fleet Quality card all work BEFORE wiring your real recap pipeline.

Run from a folder that also contains `ceo_report.py`
(copy it from ceos-enterprise/reporter/ceo_report.py), with the secret set:

    PowerShell:
        $env:CEOS_REPORT_SECRET = "<same value as REPORT_SECRET in Vercel>"
        python smoke_eval.py

Cleanup later (optional): the rows are tagged 'pipeline smoke test' in eval_runs,
so you can DELETE FROM eval_runs WHERE summary = 'pipeline smoke test'; if you want
them gone once real data flows.
"""
from ceo_report import report

samples = [0.78, 0.83, 0.80, 0.89, 0.86]  # 5 points -> score + sparkline + delta

for i, s in enumerate(samples, 1):
    ok = report(
        "finance",
        ok=True,
        summary=f"smoke test recap #{i} (q={int(s * 100)}%)",
        eval_score=s,
        eval_reliability=0.8,
        eval_summary="pipeline smoke test",
    )
    print(f"posted {s} -> {'OK' if ok else 'FAILED'}")

print(
    "\nDone. Open ceos-enterprise.vercel.app — the Finance row in the "
    "Fleet Quality card should now show ~86% with a sparkline."
)
