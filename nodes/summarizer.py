from langchain_groq import ChatGroq
from groq import RateLimitError
from config import GROQ_API_KEY
from graph.state import ResearchState
from services.text_sections import text_sections

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

def summarizer(state: ResearchState) -> dict:
    chunks = state['chunks']
    combined = "\n\n".join([chunk['chunk_text'] for chunk in chunks])

    sections = text_sections(combined)
    text = sections['head'] + "\n\n" + sections['tail']

    prompt = f"""You are a research paper analyst. You will be given key sections of a research paper.
Your task is to produce a structured summary with exactly three sections:

**Contributions**
What does this paper claim to contribute? What problem does it solve and why does it matter? List the key contributions clearly.

**Methodology**
How did the authors approach the problem? What techniques, models, datasets, or experimental setups did they use?

**Results**
What did they find? Include key metrics, comparisons, or outcomes. Be specific — do not just say "the model performed well."

Paper text:
{text}

Write the summary in clean, concise language. Do not add any section beyond the three above."""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt)
            return {'summary': response.content}
        except RateLimitError:
            return {**state, 'summary': 'Daily AI usage limit reached. Please try again later.'}
        except Exception as e:
            if attempt == max_retries - 1:
                return {**state, 'summary': f'Summary generation failed: {str(e)}'}

    return {**state, 'summary': ''}