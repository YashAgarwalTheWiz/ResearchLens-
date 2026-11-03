import re
import unicodedata

from config import EXTRACT_MAX_CHARS, IDENTITY_MAX_CHARS
from graph.state import ResearchState
from schemas.paper import (Evidence, Fact, Score, ExtractedPaper, NOT_STATED,
                           IdentityOut, OverviewOut, MethodOut, DatasetsOut,
                           ResultsOut, ClosingOut)
from services.llm_service import structured_call, RateLimited

RULES = """Rules:
- Use ONLY the text below. Do not use outside knowledge.
- For every item, 'quote' must be ONE sentence copied EXACTLY from the text (under 200 characters) that supports the value.
- If the text does not state it: return an empty list for list fields, or value "not stated in paper" with an empty quote for single fields."""

DATA_KEYWORDS = ["dataset", "data set", "benchmark", "corpus", "training set",
                 "test set", "collected", "annotated", "split"]
RESULT_KEYWORDS = ["accuracy", "outperform", "improve", "baseline", "compared",
                   "table", "hit@", "top-"]


# ---------- helpers ----------
def norm(text):
    """Keep only letters and digits so spacing, hyphenation and punctuation can't break a match."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())


def pick(chunks, sections):
    """Chunks from the wanted sections. If the paper has none of them, fall back to all chunks."""
    chosen = [c for c in chunks if c["section"] in sections]
    return chosen or chunks


def fit(sources, max_chars, keywords=None):
    """Fill the character budget with the most relevant chunks, then restore paper order."""
    ordered = sources
    if keywords:
        ordered = sorted(sources, key=lambda s: -sum(s["chunk_text"].lower().count(k) for k in keywords))
    kept, total = [], 0
    for s in ordered:
        n = len(s["chunk_text"])
        if total + n > max_chars:
            continue            # skip what doesn't fit, a smaller chunk later may
        kept.append(s)
        total += n
    kept.sort(key=lambda s: s["chunk_index"])
    return kept


def table_to_text(t):
    rows = [t["header"]] + t["rows"]
    return "\n".join(" | ".join(r) for r in rows)[:1500]


def find_evidence(quote, sources):
    """Is this quote really in one of the chunks we sent? If yes, return where."""
    q = norm(quote)
    if len(q) < 10:
        return None
    head = norm(" ".join(quote.split()[:8]))   # tolerate the LLM changing the end of a sentence
    for s in sources:
        text = norm(s["chunk_text"])
        if q in text or (len(head) >= 20 and head in text):
            return Evidence(chunk_index=s["chunk_index"], page_number=s["page_number"],
                            section=s["section"], quote=quote.strip()[:300])
    return None


def to_fact(raw, sources):
    ev = find_evidence(raw.quote, sources)
    if ev is None:
        print(f"DROPPED (quote not found): value={raw.value[:60]!r} quote={raw.quote[:120]!r}")
        return None
    return Fact(value=raw.value.strip(), evidence=[ev])


def one(raw, sources):
    return to_fact(raw, sources) or Fact(value=NOT_STATED, evidence=[])


def many(raws, sources):
    facts = [to_fact(r, sources) for r in raws]
    return [f for f in facts if f]


def numbers(text):
    """All numbers in a string, normalised: '96.4%' -> ['96.4'], '1,024' -> ['1024']."""
    return re.findall(r"\d+(?:\.\d+)?", (text or "").replace(",", ""))


def to_score(raw, sources):
    """Keep a score only if its quote is really in the paper AND its number is really in that quote.
    This stops the LLM from inventing or mis-copying results."""
    ev = find_evidence(raw.quote, sources)
    quote_numbers = numbers(raw.quote)
    value_numbers = numbers(raw.value)
    if ev is None or not value_numbers or not all(n in quote_numbers for n in value_numbers):
        print(f"DROPPED score: {raw.metric}={raw.value!r} quote={raw.quote[:120]!r}")
        return None
    # the baseline's number may sit in another row of the same table, so check the whole source chunk
    chunk = next((s for s in sources if s["chunk_index"] == ev.chunk_index
                  and s["page_number"] == ev.page_number), None)
    chunk_numbers = numbers(chunk["chunk_text"]) if chunk else quote_numbers
    baseline_numbers = numbers(raw.baseline_value)
    baseline_ok = bool(baseline_numbers) and all(n in chunk_numbers for n in baseline_numbers)
    return Score(
        metric=raw.metric.strip(), dataset=raw.dataset.strip(), value=raw.value.strip(),
        baseline=raw.baseline.strip() if baseline_ok else "",
        baseline_value=raw.baseline_value.strip() if baseline_ok else "",
        evidence=[ev],
    )


def ask(schema, instruction, sources):
    context = "\n\n".join(s["chunk_text"] for s in sources)
    prompt = f"{instruction}\n\n{RULES}\n\nText:\n{context}"
    return structured_call(schema, prompt)


# ---------- the node ----------
def extractor(state: ResearchState) -> dict:
    chunks = state["chunks"]
    # tables become pseudo-chunks (index -1) so numbers from tables can be quoted and verified too
    tables = [{"chunk_text": table_to_text(t), "page_number": t["page_number"],
               "chunk_index": -1, "section": "table"} for t in state.get("tables", [])]

    try:
        # 1. title / authors / year: first page only, cheap model
        front = fit(pick(chunks, {"front_matter", "abstract"}), IDENTITY_MAX_CHARS)
        front_text = "\n\n".join(s["chunk_text"] for s in front)
        ident = structured_call(
            IdentityOut,
            "Extract the paper's title, the list of author names, and the publication year (as text; "
            "empty string if not stated) from the beginning of this paper.\n\n" + front_text,
            fast=True,
        )

        # 2. problem + core idea <- abstract, introduction
        src = fit(pick(chunks, {"abstract", "introduction"}), EXTRACT_MAX_CHARS)
        overview = ask(
            OverviewOut,
            "problem: the problem this paper tries to solve (one sentence). "
            "core_idea: the paper's main idea or contribution (one sentence).",
            src,
        )
        problem, core_idea = one(overview.problem, src), one(overview.core_idea, src)

        # 3. method <- method section only
        src = fit(pick(chunks, {"method"}), EXTRACT_MAX_CHARS)
        meth = ask(MethodOut, "method: how the proposed approach works (1-2 sentences).", src)
        method = one(meth.method, src)

        # 3b. datasets <- anywhere a dataset could be named, most relevant chunks first
        src = fit(pick(chunks, {"introduction", "method", "experiments", "results"}),
                  EXTRACT_MAX_CHARS, DATA_KEYWORDS)
        ds = ask(
            DatasetsOut,
            "datasets: every dataset used in the experiments, one item each (value = dataset name).",
            src,
        )
        datasets = many(ds.datasets, src)

        # 4. metrics + scores + results <- tables first, then the most relevant results text
        src = fit(tables + pick(chunks, {"results", "experiments"}), EXTRACT_MAX_CHARS, RESULT_KEYWORDS)
        res = ask(
            ResultsOut,
            "metrics: the evaluation metrics used (value = metric name, e.g. 'top-1 accuracy').\n"
            "scores: up to 8 headline numbers achieved by the PROPOSED method. For each: metric (e.g. "
            "'top-1 error'), dataset (e.g. 'ImageNet val'; empty if not named), value exactly as written "
            "including % or units (e.g. '3.57%'), baseline = the strongest other method it is compared with "
            "in the same sentence or table row (empty if none), baseline_value = that method's number "
            "(empty if none). quote = the sentence or table row that contains these numbers.\n"
            "results: at most 5 headline findings about the PROPOSED method compared with baselines "
            "or alternatives. Each must be a full sentence containing the numbers, for example "
            "'Model X reaches 92.4% accuracy on dataset Y versus 90.1% for baseline Z'. "
            "Do NOT include dataset statistics, split sizes, training time or other setup details.",
            src,
        )
        metrics, results = many(res.metrics, src), many(res.results, src)
        scores = [s for s in (to_score(r, src) for r in res.scores) if s]

        # 5. limitations + future work <- discussion, conclusion
        src = fit(pick(chunks, {"discussion", "conclusion"}), EXTRACT_MAX_CHARS)
        closing = ask(
            ClosingOut,
            "limitations: limitations the AUTHORS themselves acknowledge. "
            "future_work: future directions the AUTHORS suggest. Include only what the authors say.",
            src,
        )
        limitations, future_work = many(closing.limitations, src), many(closing.future_work, src)

    except RateLimited as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Extraction failed: {e}"}

    paper = ExtractedPaper(
        title=ident.title, authors=ident.authors, year=ident.year,
        problem=problem, core_idea=core_idea, method=method, datasets=datasets,
        metrics=metrics, scores=scores, results=results, limitations=limitations, future_work=future_work,
    )
    return {"extracted": paper.model_dump()}