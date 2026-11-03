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