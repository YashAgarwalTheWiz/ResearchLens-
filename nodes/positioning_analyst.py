import re

from graph.positioning_state import PositioningState
from schemas.paper import NOT_STATED
from schemas.positioning import PositioningOut
from services.llm_service import structured_call, RateLimited


def norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def same_thing(a, b):
    a, b = norm(a), norm(b)
    return len(a) >= 3 and len(b) >= 3 and (a in b or b in a)


def coverage(rows, field, ours):
    """Count, IN CODE, which datasets/metrics the related papers use and whether ours does too.
    Counting is something code does perfectly and an LLM does badly, so we don't ask the LLM."""
    groups = []
    for row in rows:
        for name in row[field]:
            if not name or norm(name) in ("", "notstated"):
                continue
            group = next((g for g in groups if norm(g["name"]) == norm(name)), None)   # exact match only
            if group is None:
                group = {"kind": field[:-1], "name": name, "refs": []}
                groups.append(group)
            if row["ref"] not in group["refs"]:
                group["refs"].append(row["ref"])
    common = [g for g in groups if len(g["refs"]) >= 2]
    for g in common:
        # None = we can't tell (idea mode, or nothing was extracted for our paper)
        g["we_use"] = None if not ours else any(same_thing(g["name"], o) for o in ours)
    return sorted(common, key=lambda g: -len(g["refs"]))


def our_block(state):
    if state["mode"] == "idea":
        return "RESEARCH IDEA (not yet a paper):\n" + state["idea_text"]
    ex = state["extracted"]
    val = lambda f: f["value"] if f["value"] != NOT_STATED else "not stated"
    lst = lambda fs: "; ".join(f["value"] for f in fs) or "not stated"
    return (f"OUR PAPER: {ex['title']} ({ex['year']})\n"
            f"Problem: {val(ex['problem'])}\nCore idea: {val(ex['core_idea'])}\n"
            f"Method: {val(ex['method'])}\nDatasets: {lst(ex['datasets'])}\n"
            f"Metrics: {lst(ex['metrics'])}\nResults: {lst(ex['results'])}")


def positioning_analyst(state: PositioningState) -> dict:
    rows = state["related_facts"]
    papers = {p["ref"]: p for p in state["related_papers"]}

    ours_ds = ours_m = None
    if state["mode"] == "paper":
        ours_ds = [f["value"] for f in state["extracted"]["datasets"]]
        ours_m = [f["value"] for f in state["extracted"]["metrics"]]
    cov = coverage(rows, "datasets", ours_ds) + coverage(rows, "metrics", ours_m)

    when = {"earlier": ", published earlier than ours", "later": ", published later than ours",
            "same year": ", published the same year as ours", "unknown": ""}
    table = "\n".join(
        f"[{r['ref']}] {papers[r['ref']]['title']} ({papers[r['ref']]['year']}{when[papers[r['ref']]['relation']]})"
        f" | task: {r['task']} | method: {r['method']} | "
        f"datasets: {', '.join(r['datasets']) or '-'} | result: {r['key_result']}"
        for r in rows
    )
    cov_text = "\n".join(
        f"- {g['kind']} '{g['name']}' used by {len(g['refs'])} related papers ({', '.join(g['refs'])})"
        + ("" if g["we_use"] is None else f"; used by ours: {'yes' if g['we_use'] else 'NO'}")
        for g in cov
    ) or "- none"

    prompt = f"""You are helping a researcher see where a piece of work stands against related work.

{our_block(state)}

RELATED PAPERS (facts taken from their abstracts):
{table}

FIELD COVERAGE (counted by code, trust these numbers):
{cov_text}

Produce:
1. summary: 2-3 sentences on how this work relates to the related papers. Cite papers inline like [P3].
2. contributions: for each main contribution of OUR work (max 4): the claim, the closest related papers
   (closest_refs), how ours differs, and overlap = low / partial / high. Prefer papers published earlier
   than ours when judging if something was already done.
3. gaps: max 5 gaps of OUR work compared with the related papers — e.g. common datasets or metrics it
   skips, settings others test that it doesn't, or questions none of the papers answer. Each gap must
   cite the related papers that support it in refs.

Rules:
- Only use refs from the list above (P1, P2, ...). Never invent papers.
- Every contribution and every gap MUST cite at least one ref.
- Only say what the facts above support. If unsure, leave it out."""

    try:
        out = structured_call(PositioningOut, prompt)
    except RateLimited as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Positioning analysis failed: {e}"}

    return {"coverage": cov, "analysis": out.model_dump()}