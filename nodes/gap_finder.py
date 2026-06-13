from langchain_groq import ChatGroq
from groq import RateLimitError
from config import GROQ_API_KEY
from graph.state import ResearchState
from pydantic import BaseModel
from typing import List


class ResearchGaps(BaseModel):
    gaps: List[str]


llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)


def gap_finder(state: ResearchState) -> dict:

    max_retries = 3
    response = None

    structured_llm = llm.with_structured_output(ResearchGaps)
    combined = "\n\n".join([chunk['chunk_text'] for chunk in state['chunks']])
    combined = combined[:30000]
    prompt = f"""You are a critical research analyst. You will be given the text of a research paper.

    Identify all research gaps in the paper. Look for:
    - Explicit limitations acknowledged by the authors
    - Untested domains or datasets
    - Open questions left unanswered
    - Suggested future work
    - Assumptions that were never validated

    Return each gap as a separate, self-contained statement.
    {combined}
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

    return {**state, 'research_gaps': response.gaps}