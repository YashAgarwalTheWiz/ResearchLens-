from graph.positioning_state import PositioningState
from schemas.positioning import RelatedFactsOut
from services.llm_service import structured_call, RateLimited


def related_extractor(state: PositioningState) -> dict:
    papers = state["related_papers"]
    known = {p["ref"] for p in papers}

    block = "\n\n".join(
        f"[{p['ref']}] {p['title']} ({p['year']})\n{p['abstract']}" for p in papers
    )
    prompt = f"""For EACH paper below, extract from its abstract:
- task: the problem it tackles (short phrase)
- method: its approach (one short sentence)
- datasets: dataset names it uses (empty list if none named)
- metrics: evaluation metric names (empty list if none named)
- key_result: its main reported result, with numbers if given (one sentence)

Rules:
- Use ONLY the abstract of that paper. No outside knowledge.
- If something is not in the abstract, write "not stated" (or an empty list).
- Return one row per paper, with 'ref' exactly as given (P1, P2, ...).

Papers:
{block}"""

    try:
        out = structured_call(RelatedFactsOut, prompt)
    except RateLimited as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Reading related papers failed: {e}"}

    # grounding: keep only rows that point at a paper we really retrieved, one row per paper
    rows, seen = [], set()
    for row in out.papers:
        if row.ref in known and row.ref not in seen:
            rows.append(row.model_dump())
            seen.add(row.ref)
    return {"related_facts": rows}