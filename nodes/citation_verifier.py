import re
from datetime import datetime, timezone

from graph.positioning_state import PositioningState

REF_PATTERN = re.compile(r"\[(P\d+)\]")


def citation_verifier(state: PositioningState) -> dict:
    """Grounding check done in CODE: every claim must point at a paper we actually retrieved.
    Claims citing nothing real are dropped; links are built from real IDs, never taken from the LLM."""
    papers = {p["ref"]: p for p in state["related_papers"]}
    facts = {r["ref"]: r for r in state.get("related_facts", [])}
    analysis = state["analysis"]
    dropped = []

    def source(ref):
        p = papers[ref]
        return {"ref": ref, "title": p["title"], "year": p["year"], "url": p["url"]}

    def real_refs(refs):
        return [r for r in dict.fromkeys(refs) if r in papers]   # dedupe, keep order

    contributions = []
    for c in analysis["contributions"]:
        refs = real_refs(c["closest_refs"])
        if not refs:
            dropped.append(c["claim"])
            continue
        contributions.append({**c, "closest_refs": refs, "sources": [source(r) for r in refs]})

    gaps = []
    for g in analysis["gaps"]:
        refs = real_refs(g["refs"])
        if not refs:
            dropped.append(g["gap"])
            continue
        gaps.append({**g, "refs": refs, "sources": [source(r) for r in refs]})

    # summary: turn real [P3] into links, remove any [P99] the model invented
    def link(m):
        ref = m.group(1)
        return f"[[{ref}]]({papers[ref]['url']})" if ref in papers else ""
    summary = REF_PATTERN.sub(link, analysis["summary"])
    summary = re.sub(r"[ \t]+([.,;:])", r"\1", summary).replace("  ", " ").strip()   # tidy gaps left behind

    related = [{**p, "facts": facts.get(p["ref"])} for p in state["related_papers"]]

    return {"positioning": {
        "mode": state["mode"],
        "self_paper_id": state.get("self_paper_id", ""),
        "search_queries": state.get("search_queries", []),
        "summary": summary,
        "contributions": contributions,
        "gaps": gaps,
        "coverage": state.get("coverage", []),
        "related": related,
        "dropped_claims": dropped,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }}