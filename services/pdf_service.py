import fitz
from graph.state import CitationObject
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
def parse_pdf(pdf_path):
    doc=fitz.open(pdf_path)
    chunk_index=0
    result=[]
    for page_num,page in enumerate(doc):
        chunks=splitter.split_text(page.get_text())
        for chunk in chunks:
            result.append({'chunk_text':chunk,'page_number':page_num+1,'chunk_index':chunk_index})
            chunk_index=chunk_index+1
    return result
