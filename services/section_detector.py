import re
from collections import Counter

# 1. The names we recognise. Left = the label we store, right = ways papers write it.
SECTION_NAMES = {
    "abstract": {"abstract"},
    "introduction": {"introduction"},
    "related_work": {"related work", "related works", "background",
                     "preliminaries", "literature review"},
    "method": {"method", "methods", "methodology", "approach",
               "proposed method", "proposed approach", "model", "our approach"},
    "experiments": {"experiments", "experimental setup", "experimental results",
                    "evaluation", "experiments and results"},
    "results": {"results", "results and discussion", "analysis"},
    "discussion": {"discussion", "limitations", "limitations and future work"},
    "conclusion": {"conclusion", "conclusions", "conclusion and future work",
                   "conclusions and future work", "future work"},
    "references": {"references", "bibliography"},
    "acknowledgments": {"acknowledgments", "acknowledgements", "acknowledgment"},
}

# sections whose text we do NOT want to embed
DROP_SECTIONS = {"references", "acknowledgments"}
SECTION_ORDER = {
    "front_matter": 0, "abstract": 1, "introduction": 2, "related_work": 3,
    "method": 4, "experiments": 5, "results": 6, "discussion": 7,
    "conclusion": 8, "references": 9, "acknowledgments": 10, "appendix": 11,
}

# "3." / "3.1" / "III." / "A." at the start of a line
NUMBER_PREFIX = re.compile(r"^(\d+(\.\d+)*\.?|[ivxlc]+\.|[A-Z]\.)\s+", re.IGNORECASE)
NUMBER_ONLY = re.compile(r"^(\d+(\.\d+)*\.?|[ivxlc]+\.?)$", re.IGNORECASE)


def normalize_heading(text):
    """'3.1. Experiments:' -> 'experiments'. Numbering is optional."""
    t = text.strip()
    t = NUMBER_PREFIX.sub("", t)
    return t.strip().rstrip(":.").lower()


def match_section(text):
    """Return the canonical section name, or None if this line is not a known heading."""
    name = normalize_heading(text)
    if len(name) > 60:
        return None
    for label, variants in SECTION_NAMES.items():
        if name in variants:
            return label
    # "Appendix", "Appendix A", "Appendix B: Proofs" - startswith is OK here
    if name.startswith("appendix"):
        return "appendix"
    return None


def is_top_level_numbered(text):
    """'3. Deep Residual Learning' -> True. '3.1. Residual Learning' -> False."""
    m = re.match(r"^(\d+|[ivxlc]+)\.?\s+\S", text.strip(), re.IGNORECASE)
    return bool(m)


def _is_bold(span):
    font = span["font"].lower()
    return bool(span["flags"] & 16) or "bold" in font or "cmbx" in font


def get_lines(page):
    """Turn a PyMuPDF page into a list of {'text','size','bold'} lines, in PDF reading order."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:  # 0 = text block, 1 = image
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            lines.append({
                "text": "".join(s["text"] for s in line["spans"]).strip(),
                "size": max(s["size"] for s in spans),
                "bold": all(_is_bold(s) for s in spans),
            })
    return lines


def body_font_size(pages_lines):
    """Most common font size, weighted by characters = the size of normal paragraph text."""
    counts = Counter()
    for lines in pages_lines:
        for ln in lines:
            counts[round(ln["size"], 1)] += len(ln["text"])
    return counts.most_common(1)[0][0] if counts else 10.0


def looks_like_heading(line, body_size):
    """Headings are bold OR clearly bigger than body text. Figure labels are neither."""
    return line["bold"] or line["size"] >= body_size + 1.0


def detect_sections(pages_lines, drop=DROP_SECTIONS):
    """
    pages_lines: list (one per page) of lines from get_lines().
    drop: sections to leave out (by default references + acknowledgments).
    Returns a list of segments: {'section', 'page_number', 'text'}.
    """
    body = body_font_size(pages_lines)
    segments = []
    current = "front_matter"
    prev_known = None  # last recognised section, used for unknown headings

    for page_idx, lines in enumerate(pages_lines):
        buffer = []

        def flush():
            if buffer and current not in drop:
                segments.append({
                    "section": current,
                    "page_number": page_idx + 1,
                    "text": "\n".join(buffer),
                })
            buffer.clear()

        for line in lines:
            text = line["text"]
            label = match_section(text) if looks_like_heading(line, body) else None

            # A numbered heading we do not recognise, e.g. "3. Deep Residual Learning".
            # If it sits between intro/related-work and experiments, it is the method.
            if (label is None and looks_like_heading(line, body)
                    and is_top_level_numbered(text) and not NUMBER_ONLY.match(text)
                    and len(text) < 80 and prev_known in {"introduction", "related_work"}):
                label = "method"
            if label and SECTION_ORDER[label] < SECTION_ORDER[current]:
                label = None   # going backwards = false heading
            if label:
                flush()
                current = label
                prev_known = label
            buffer.append(text)
        flush()
    return segments