"""Check a paper's own reference list against OpenAlex.

1. Pull the reference list out of the stored PDF.
2. The fast LLM splits it into (title, first author, year) — in pieces, to stay inside token limits.
3. Code checks each parsed title really appears in the reference text (catches LLM mistakes).
4. Each title is looked up on OpenAlex and compared IN CODE: title similarity, year, first author.
"""
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from schemas.references import ParsedRefsOut
from services import openalex_service as oa
from services.llm_service import structured_call
from services.pdf_service import extract_references

PIECE_CHARS = 6000      # reference text sent to the LLM per call
MAX_REFERENCES = 60     # cap OpenAlex lookups per paper


def norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def title_similarity(a, b):
    clean = lambda t: " ".join(re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split())
    a, b = clean(a), clean(b)
    short, long_ = sorted((a, b), key=len)
    # references often drop a subtitle ("Batch Normalization: Accelerating ..." without "by Reducing ...")
    if len(short.split()) >= 4 and short in long_:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def split_into_pieces(text, size=PIECE_CHARS):
    """Cut on line breaks so a reference is rarely split in half."""
    pieces, current = [], ""
    for line in text.splitlines():
        if len(current) + len(line) > size and current:
            pieces.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        pieces.append(current)
    return pieces


def parse_references(text):
    refs, seen = [], set()
    for piece in split_into_pieces(text):
        out = structured_call(
            ParsedRefsOut,
            "Below is part of a research paper's reference list. For EVERY reference return:\n"
            "- title: the title of the cited work, copied exactly (not the venue, not the authors)\n"
            "- first_author: surname of the first author only\n"
            "- year: publication year as written, or empty string\n"
            "Skip fragments that are not a complete reference.\n\n" + piece,
            fast=True,
        )
        piece_norm = norm(piece)
        for r in out.references:
            key = norm(r.title)
            # grounding: the title must really be in the text (stops invented or garbled titles)
            if len(key) < 10 or key not in piece_norm or key in seen:
                continue
            seen.add(key)
            refs.append(r)
    return refs


def check_one(ref):
    year = int(ref.year) if re.fullmatch(r"(19|20)\d{2}", ref.year.strip()) else None
    candidates = oa.find_by_title(ref.title)
    best = max(candidates, key=lambda w: title_similarity(ref.title, w["title"]), default=None)
    score = title_similarity(ref.title, best["title"]) if best else 0.0

    row = {"title": ref.title, "first_author": ref.first_author, "year": ref.year,
           "match": None, "similarity": round(score, 2), "status": "not_found", "issues": []}

    if not best or score < 0.75:
        return row

    row["match"] = {"title": best["title"], "year": best["year"], "url": best["url"],
                    "authors": best["authors"][:3]}
    issues = []
    if score < 0.9:
        issues.append("title differs from the indexed paper")
    if year and best["year"] and abs(year - best["year"]) > 1:
        issues.append(f"year: cited {year}, indexed {best['year']}")
    surname = norm(ref.first_author)
    if surname and best["authors"] and not any(surname in norm(a) for a in best["authors"]):
        issues.append(f"first author '{ref.first_author}' not among the indexed authors")
    row["issues"] = issues
    row["status"] = "check" if issues else "verified"
    return row


def check_references(pdf_path):
    text = extract_references(pdf_path)
    if not text.strip():
        return {"error": "Couldn't find a reference list in this PDF."}

    refs = parse_references(text)
    if not refs:
        return {"error": "Found the reference section but couldn't read individual references."}

    rows = [check_one(r) for r in refs[:MAX_REFERENCES]]
    counts = {s: sum(r["status"] == s for r in rows) for s in ("verified", "check", "not_found")}
    return {
        "references": rows,
        "counts": counts,
        "total": len(rows),
        "skipped": max(0, len(refs) - MAX_REFERENCES),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }