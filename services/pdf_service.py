import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.section_detector import get_lines, detect_sections

splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)


def parse_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    pages_lines = [get_lines(page) for page in doc]
    segments = detect_sections(pages_lines)

    result = []
    chunk_index = 0
    for seg in segments:
        for chunk in splitter.split_text(seg["text"]):
            result.append({
                "chunk_text": chunk,
                "page_number": seg["page_number"],
                "chunk_index": chunk_index,
                "section": seg["section"],
            })
            chunk_index += 1
    return result


REFERENCE_HEADINGS = {"references", "bibliography", "reference"}


def extract_references(pdf_path, max_chars=30000):
    """The paper's reference list as plain text ('' if we can't find one)."""
    doc = fitz.open(pdf_path)
    pages_lines = [get_lines(page) for page in doc]

    # 1. normal case: the section detector found a 'References' heading
    segments = detect_sections(pages_lines, drop={"acknowledgments"})
    text = "\n".join(seg["text"] for seg in segments if seg["section"] == "references")

    # 2. fallback: take everything after the LAST line that just says "References"
    if not text.strip():
        lines = [ln["text"] for page in pages_lines for ln in page]
        starts = [i for i, t in enumerate(lines) if t.strip().rstrip(":").lower() in REFERENCE_HEADINGS]
        if starts:
            text = "\n".join(lines[starts[-1] + 1:])

    return text[:max_chars]