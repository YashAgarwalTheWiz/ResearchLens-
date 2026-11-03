"""Measure the 'Where It Stands' feature on every paper you've analysed.

Run from the project root:  python -m eval.grounding_eval

1. Grounding rate: share of LLM claims that cited a REAL retrieved paper (the rest were dropped
   by citation_verifier). Computed automatically.
2. Related-paper precision: are the 10 papers actually related? Needs YOUR judgement:
   the first run writes eval/related_labels.csv -> fill the 'relevant' column with y or n
   -> run again to get precision.
"""
import csv
import os

from services.db import get_connection, loads

LABELS = "eval/related_labels.csv"

conn = get_connection()
rows = conn.execute(
    "SELECT session_id, pdf_name, positioning FROM rpa_sessions WHERE positioning IS NOT NULL"
).fetchall()
conn.close()

if not rows:
    raise SystemExit("No analysed papers yet. Open a paper and run 'Analyze related work' first.")

# ---------- 1. grounding rate ----------
total_kept = total_dropped = 0
print(f"{'paper':45} kept  dropped  grounded")
for session_id, pdf_name, raw in rows:
    pos = loads(raw, {})
    kept = len(pos.get("contributions", [])) + len(pos.get("gaps", []))
    dropped = len(pos.get("dropped_claims", []))
    total_kept, total_dropped = total_kept + kept, total_dropped + dropped
    rate = kept / (kept + dropped) if kept + dropped else 1.0
    print(f"{pdf_name[:45]:45} {kept:4}  {dropped:7}  {rate:7.0%}")

overall = total_kept / (total_kept + total_dropped) if total_kept + total_dropped else 1.0
print(f"\nOverall grounding rate: {overall:.1%} ({total_kept} kept, {total_dropped} dropped) "
      f"across {len(rows)} papers\n")

# ---------- 2. related-paper precision ----------
labels = {}
if os.path.exists(LABELS):
    with open(LABELS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            labels[(r["session_id"], r["paper_id"])] = r["relevant"].strip().lower()

out = []
for session_id, pdf_name, raw in rows:
    for p in loads(raw, {}).get("related", []):
        out.append({
            "session_id": session_id, "our_paper": pdf_name, "ref": p["ref"], "paper_id": p["paper_id"],
            "title": p["title"], "year": p["year"], "similarity": p["similarity"],
            "relevant": labels.get((session_id, p["paper_id"]), ""),   # keep labels you already filled
        })

os.makedirs(os.path.dirname(LABELS), exist_ok=True)
with open(LABELS, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    writer.writeheader()
    writer.writerows(out)

judged = [r for r in out if r["relevant"] in ("y", "n")]
if not judged:
    print(f"Related-paper precision: not labelled yet. Open {LABELS}, put y or n in the 'relevant' "
          f"column for each row, then run this again.")
else:
    hits = sum(r["relevant"] == "y" for r in judged)
    print(f"Related-paper precision: {hits / len(judged):.1%} ({hits} of {len(judged)} judged papers are relevant)")
    if len(judged) < len(out):
        print(f"({len(out) - len(judged)} rows still unlabelled in {LABELS})")