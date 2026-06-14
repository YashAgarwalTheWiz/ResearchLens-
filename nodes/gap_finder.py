from langchain_groq import ChatGroq
from groq import RateLimitError
from config import GROQ_API_KEY,GAP_MAX_CHARS
from graph.state import ResearchState
from pydantic import BaseModel
from typing import List
from services.text_sections import text_sections

class ResearchGaps(BaseModel):
    gaps: List[str]


llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)


def gap_finder(state: ResearchState) -> dict:

    max_retries = 3
    response = None

    structured_llm = llm.with_structured_output(ResearchGaps)
    combined = "\n\n".join([chunk['chunk_text'] for chunk in state['chunks']])
    middle_text=text_sections(combined)['middle']
    middle_text=middle_text[:GAP_MAX_CHARS]

    prompt = f"""You are a critical research analyst. You are given the MIDDLE section of a research paper — the body between the introduction and the conclusion.

    Your task is to identify research gaps embedded within the methodology and findings. Look for:
    - Untested domains, datasets, or conditions the experiments did not cover
    - Assumptions made by the authors that were never validated or tested
    - Open questions raised within the paper body but left unanswered
    - Weaknesses or gaps in the experimental design or evaluation

    Do NOT include limitations or future work explicitly stated by the authors — those are captured separately.
    Return each gap as a separate, self-contained statement.

    {middle_text}
    """

    for attempt in range(max_retries):
        try:
            response = structured_llm.invoke(prompt)
            break
        except RateLimitError:
            return {**state, "error": "Daily AI usage limit reached. Please try again later or contact the admin."}
        except Exception as e:
            if attempt == max_retries - 1:
                return {**state, "error": f"Gap analysis failed: {str(e)}"}

    if response is None:
        return {**state, "error": "Gap analysis failed after multiple attempts."}
    metadata_gaps=state['metadata']['limitations'] + state['metadata']['future_work']
    all_gaps=metadata_gaps + response.gaps
    return {**state, 'research_gaps': all_gaps}