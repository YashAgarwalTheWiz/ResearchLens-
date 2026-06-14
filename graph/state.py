from typing import TypedDict,List

class PaperMetadata(TypedDict):
    title:str
    authors:List[str]
    year:str
    dataset:List[str]
    methodology:str
    metrics:List[str]
    limitations:List[str]
    future_work:List[str]

class CitationObject(TypedDict):
    chunk_text:str
    page_number:int
    chunk_index:int

class RetrievedDoc(TypedDict):
    chunk_text:str
    page_number:int
    chunk_index:int
    relevance_score:float

class ResearchState(TypedDict):
    metadata:PaperMetadata
    session_id: str
    pdf_path:str
    query:str
    query_type:str
    chunks:List[CitationObject]
    retrieved_docs:List[RetrievedDoc]
    web_search_triggered:bool
    summary:str
    research_gaps:List
    answer:str
    citations:List[CitationObject]
    chat_history:List
    
