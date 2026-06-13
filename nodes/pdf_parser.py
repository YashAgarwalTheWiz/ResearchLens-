from services.pdf_service import parse_pdf
from graph.state import ResearchState

def pdf_parser(state:ResearchState)->dict:
    result=parse_pdf(state['pdf_path'])
    return {'chunks':result}