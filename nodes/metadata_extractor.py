from langchain_groq import ChatGroq
from groq import RateLimitError
from config import GROQ_API_KEY
from graph.state import ResearchState
from pydantic import BaseModel
from typing import List
from services.text_sections import text_sections

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

class PaperMetadataSchema(BaseModel):
    title:str
    authors:List[str]
    year:str
    dataset:List[str]
    methodology:str
    metrics:List[str]
    limitations:List[str]
    future_work:List[str]

def metadata_extractor(state:ResearchState)->dict:
    combined='\n\n'.join([chunk['chunk_text'] for chunk in state['chunks']])
    sections = text_sections(combined)
    head_text = sections["head"]
    tail_text = sections["tail"]
    structured_llm=llm.with_structured_output(PaperMetadataSchema)
    prompt=f"""You are a research paper analyst. You will be given two excerpts from a research paper:
    the beginning section, and the ending section (which excludes the references/bibliography list).

    Beginning of paper:
    {head_text}

    Ending of paper (before references):
    {tail_text}

    Extract the following information:
    - title: the full title of the paper
    - authors: a list of all author names
    - year: the publication year, as text (e.g. "2023")
    - dataset: a list of all datasets used or mentioned
    - methodology: a concise description of the methods, models, or experimental approach used
    - metrics: a list of key results/metrics, each as a self-contained statement (e.g. "Achieved 92.4% accuracy on CIFAR-10")
    - limitations: a list of limitations explicitly acknowledged by the authors, each as a self-contained statement
    - future_work: a list of future work directions suggested by the authors, each as a self-contained statement

    If a field cannot be determined from the given text, return an empty list (for list fields) or an empty string (for the string fields). Do not guess or fabricate information."""

    max_retries=3
    response=None

    for attempt in range(max_retries):
        try:
            response=structured_llm.invoke(prompt)
            break
        except RateLimitError:
            return {**state,'error':'Daily AI usage limit reached. Please try again later or contact the admin'}
        except Exception as e:
            if attempt==max_retries-1:
                return {**state,'error':f'Metadata extraction failed:{str(e)}'}
    if response is None:
        return {**state,'error':'Metadata extraction failed after multiple attempts'}
    return {**state,'metadata':response.model_dump()}