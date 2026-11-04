import re
from datetime import date
from difflib import SequenceMatcher

import numpy as np

from config import RELATED_TOP_K, RELATED_ABSTRACT_CHARS, MAX_CANDIDATES
from graph.positioning_state import PositioningState
from schemas.paper import NOT_STATED
from schemas.positioning import SearchQueriesOut
from services import openalex_service as oa
from services.embedding_service import get_embeddings
from services.llm_service import structured_call, RateLimited


def same_title(a, b):
    clean = lambda t: re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()
    return SequenceMatcher(None, clean(a), clean(b)).ratio() >= 0.9


def describe_our_work(state):
    """One block of text that describes 'our work' — used to search and to rank."""
    if state["mode"] == "idea":
        return state["idea_text"].strip(), None, None

    ex = state["extracted"]
    parts = [ex.get("title", "")]
    for key in ("problem", "core_idea", "method"):
        value = ex.get(key, {}).get("value", "")
        if value and value != NOT_STATED:
            parts.append(value)
    year = re.search(r"(19|20)\d{2}", ex.get("year") or "")
    return " ".join(p for p in parts if p), ex.get("title"), int(year.group()) if year else None


def relation(year, our_year):
    if not year or not our_year:
        return "unknown"
    return "earlier" if year < our_year else "same year" if year == our_year else "later"


CITATION_BOOST = 0.02   # small tie-breaker: a well-cited paper edges out an equally similar obscure one


def cosine_rank(our_text, papers):
    """Rank by meaning first; citations only break near-ties (log scale, so 10 vs 1000 citations
    adds ~0.09 at most). The returned score is the pure similarity, so the UI stays honest."""
    docs = [f"{p['title']}. {p['abstract']}"[:2000] for p in papers]
    q = np.array(get_embeddings([our_text], input_type="search_query")[0])
    d = np.array(get_embeddings(docs, input_type="search_document"))
    sims = d @ q / (np.linalg.norm(d, axis=1) * np.linalg.norm(q) + 1e-9)
    boost = np.array([CITATION_BOOST * np.log1p(p.get("citation_count") or 0) for p in papers])
    order = np.argsort(-(sims + boost))
    return [(float(sims[i]), papers[i]) for i in order]


PER_QUERY = 2       # every search query is guaranteed this many places in the final list
NUM_QUERIES = 5     # one per part of the work: task, method, language/data, setting, evaluation
RECENT_YEARS = 5    # each query is also searched within the last N years, so new work isn't buried


def pick_diverse(ranked, hits_by_query, k=RELATED_TOP_K, per_query=PER_QUERY):
    """Don't let one theme crowd out the rest: first take the best `per_query` papers found by EACH
    query, then fill the remaining places by overall rank. Final list stays in overall rank order."""
    position = {p["id"]: i for i, (_, p) in enumerate(ranked)}
    chosen = set()
    for ids in hits_by_query.values():
        found = sorted((position[i] for i in set(ids) if i in position), key=int)
        for pos in [x for x in found if x not in chosen][:per_query]:
            if len(chosen) < k:
                chosen.add(pos)
    for pos in range(len(ranked)):
        if len(chosen) >= k:
            break
        chosen.add(pos)
    return [ranked[pos] for pos in sorted(chosen)]


def related_finder(state: PositioningState) -> dict:
    try:
        our_text, our_title, our_year = describe_our_work(state)
        if len(our_text) < 30:
            return {"error": "Not enough information to search for related work."}

        # 1. short keyword queries, one per distinct part of the work (cheap model, one call)
        queries = structured_call(
            SearchQueriesOut,
            f"Write {NUM_QUERIES} search queries to find published research papers related to the work below.\n"
            "Rules:\n"
            "- Each query is 2-5 words.\n"
            "- Use the standard technical terms researchers put in paper TITLES, not phrases copied from "
            "the description. Examples: 'automatic question generation', 'Indic language models', "
            "'post-OCR error correction', 'on-device language models', 'citation verification'.\n"
            "- Each query covers ONE different part of the work: the main task, the method or model, "
            "the input/data (e.g. OCR, scanned documents), the language or domain, and the setting or "
            "evaluation. Don't leave out any important part.\n"
            "- Plain words only: no quotes, no AND/OR.\n\n"
            "Work:\n" + our_text[:2000],
            fast=True,
        ).queries[:NUM_QUERIES]

        # 2. is our paper itself on OpenAlex?
        self_id = None
        if our_title:
            for hit in oa.search(our_title, per_page=5):
                if same_title(hit["title"], our_title):
                    self_id = hit["id"]
                    break

        # 3. collect candidate IDs from every route, remembering how we found each one
        candidates = {}   # work_id -> set of "how we found it"

        def add(ids, via):
            for wid in ids:
                if wid:
                    candidates.setdefault(wid, set()).add(via)

        if self_id:
            work = oa.get_work(self_id) or {}
            add(work.get("referenced_works", []), "cited by this paper")
            add(work.get("related_works", []), "related (OpenAlex)")
            add([p["id"] for p in oa.citing_works(self_id)], "cites this paper")

        # each query twice: all years (classics) + recent years only (so new work isn't buried)
        recent_from = date.today().year - RECENT_YEARS
        search_hits, hits_by_query = [], {}
        for q in queries:
            hits = oa.search(q, per_page=15) + oa.search(q, per_page=15, since_year=recent_from)
            search_hits.extend(hits)
            hits_by_query[q] = [h["id"] for h in hits]
            add(hits_by_query[q], "search")

        if not self_id:
            # our paper isn't indexed (or it's just an idea): borrow OpenAlex's
            # "related works" from the top search hits instead
            for hit in search_hits[:3]:
                work = oa.get_work(hit["id"]) or {}
                add(work.get("related_works", []), "related (OpenAlex)")

        # 4. drop our own paper
        candidates.pop(self_id, None)
        if not candidates:
            return {"error": "Couldn't find any related papers on OpenAlex."}

        # 5. fetch abstracts (100 per call), keep only papers we can actually read,
        #    and drop other versions of our own paper (e.g. arXiv vs conference)
        full = [p for p in oa.details(list(candidates)[:MAX_CANDIDATES])
                if p["abstract"] and not (our_title and same_title(p["title"], our_title))]
        if not full:
            return {"error": "Related papers were found, but none had an abstract to compare against."}

        # 6. rank by meaning, then keep the top K while making sure every query's theme is represented
        ranked = pick_diverse(cosine_rank(our_text, full), hits_by_query)

    except RateLimited as e:
        return {"error": str(e)}
    except oa.OpenAlexError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Related-paper search failed: {e}"}

    related = []
    for i, (score, p) in enumerate(ranked, start=1):
        related.append({
            "ref": f"P{i}",
            "paper_id": p["id"],
            "title": p["title"],
            "year": p["year"],
            "venue": p["venue"],
            "citation_count": p["citation_count"],
            "url": p["url"],
            "abstract": p["abstract"][:RELATED_ABSTRACT_CHARS],
            "similarity": round(score, 3),
            "relation": relation(p["year"], our_year),
            "found_via": sorted(candidates.get(p["id"], [])),
        })

    return {"our_text": our_text, "our_year": our_year, "search_queries": queries,
            "self_paper_id": self_id or "", "related_papers": related}