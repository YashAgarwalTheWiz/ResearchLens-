import re
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


def cosine_rank(our_text, papers):
    docs = [f"{p['title']}. {p['abstract']}"[:2000] for p in papers]
    q = np.array(get_embeddings([our_text], input_type="search_query")[0])
    d = np.array(get_embeddings(docs, input_type="search_document"))
    scores = d @ q / (np.linalg.norm(d, axis=1) * np.linalg.norm(q) + 1e-9)
    return [(float(s), p) for s, p in sorted(zip(scores, papers), key=lambda x: -x[0])]


def related_finder(state: PositioningState) -> dict:
    try:
        our_text, our_title, our_year = describe_our_work(state)
        if len(our_text) < 30:
            return {"error": "Not enough information to search for related work."}

        # 1. three short keyword queries (cheap model, one call)
        queries = structured_call(
            SearchQueriesOut,
            "Write 3 different keyword search queries (3-8 words each) that would find research papers "
            "on the same problem or using the same approach as the work below. Plain words only: "
            "no quotes, no AND/OR.\n\nWork:\n" + our_text[:2000],
            fast=True,
        ).queries[:3]

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

        search_hits = []
        for q in queries:
            hits = oa.search(q)
            search_hits.extend(hits)
            add([h["id"] for h in hits], "search")

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

        # 6. rank by meaning, not by keywords, and keep the top K
        ranked = cosine_rank(our_text, full)[:RELATED_TOP_K]

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