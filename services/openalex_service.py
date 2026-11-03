import time
import requests

from config import OPENALEX_API_KEY

BASE = "https://api.openalex.org"

LIGHT_FIELDS = "id,display_name,publication_year"
DETAIL_FIELDS = "id,display_name,publication_year,doi,cited_by_count,abstract_inverted_index,primary_location"
WORK_FIELDS = "id,display_name,publication_year,referenced_works,related_works"

MIN_GAP = 0.1      # a free key allows ~30 requests/second; we stay well under that
_last_call = 0.0
_cache = {}        # same request -> same answer, no new API call (and no credits spent)


class OpenAlexError(Exception):
    pass


def _get(path, params=None, retries=4):
    global _last_call
    params = dict(params or {})
    key = f"{path}|{sorted(params.items())}"
    if key in _cache:
        return _cache[key]
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    for attempt in range(retries):
        wait = MIN_GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()

        r = requests.get(BASE + path, params=params, timeout=30)
        if r.status_code == 200:
            _cache[key] = r.json()
            return _cache[key]
        if r.status_code == 404:          # "not found" is an answer, not an error
            return None
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 * (2 ** attempt))  # back off: 2s, 4s, 8s, 16s
            continue
        raise OpenAlexError(f"OpenAlex error {r.status_code}: {r.text[:200]}")
    raise OpenAlexError("OpenAlex is rate-limiting us (or today's free budget is used up). Try again later.")


# ---------- helpers: turn OpenAlex's format into ours ----------
def short_id(openalex_id):
    """'https://openalex.org/W2741809807' -> 'W2741809807'"""
    return (openalex_id or "").rsplit("/", 1)[-1]


def rebuild_abstract(inverted):
    """OpenAlex stores abstracts as {word: [positions]} (for legal reasons). Put the words back in order."""
    if not inverted:
        return ""
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def paper_url(work_id, doi=None):
    """We build links ourselves from real API data, so a link can never be made up."""
    return doi if doi else f"https://openalex.org/works/{work_id}"


def to_paper(w):
    """One OpenAlex work -> the same simple dict the rest of our code uses."""
    source = ((w.get("primary_location") or {}).get("source") or {})
    wid = short_id(w.get("id"))
    return {
        "id": wid,
        "title": w.get("display_name") or "",
        "year": w.get("publication_year"),
        "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
        "venue": source.get("display_name") or "",
        "citation_count": w.get("cited_by_count") or 0,
        "url": paper_url(wid, w.get("doi")),
    }


def _list(params):
    data = _get("/works", params)
    return [to_paper(w) for w in (data or {}).get("results") or []]


# ---------- the calls our nodes use ----------
def search(query, per_page=20):
    """Keyword search over titles + abstracts."""
    return _list({"search": query, "per_page": per_page, "select": LIGHT_FIELDS})


def get_work(work_id):
    """One work with the IDs of its references and OpenAlex's 'related works'. Single lookups are free."""
    data = _get(f"/works/{work_id}", {"select": WORK_FIELDS})
    if not data:
        return None
    return {
        "id": short_id(data.get("id")),
        "title": data.get("display_name") or "",
        "year": data.get("publication_year"),
        "referenced_works": [short_id(x) for x in data.get("referenced_works") or []],
        "related_works": [short_id(x) for x in data.get("related_works") or []],
    }


def citing_works(work_id, per_page=100):
    """Works that cite this work, most-cited first."""
    return _list({"filter": f"cites:{work_id}", "per_page": per_page,
                  "sort": "cited_by_count:desc", "select": LIGHT_FIELDS})


def details(work_ids):
    """Full details (abstract, venue, DOI, ...) for many works, 100 per call."""
    papers = []
    for i in range(0, len(work_ids), 100):
        batch = work_ids[i:i + 100]
        papers += _list({"filter": "openalex:" + "|".join(batch), "per_page": 100, "select": DETAIL_FIELDS})
    return papers