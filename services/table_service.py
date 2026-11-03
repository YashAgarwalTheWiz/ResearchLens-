import fitz


def extract_tables(pdf_path, pages):
    """pages: set of 1-based page numbers worth scanning (Results/Experiments pages)."""
    doc = fitz.open(pdf_path)
    tables = []
    for page_number in sorted(pages):
        page = doc[page_number - 1]
        for t in page.find_tables().tables:
            rows = [[(cell or "").strip() for cell in row] for row in t.extract()]
            if len(rows) < 2 or len(rows[0]) < 2:   # skip 1-row / 1-column false positives
                continue
            tables.append({
                "page_number": page_number,
                "header": rows[0],
                "rows": rows[1:],
            })
    return tables