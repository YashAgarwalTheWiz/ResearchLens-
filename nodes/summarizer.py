from langchain_groq import ChatGroq
from config import GROQ_API_KEY
from graph.state import ResearchState

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

def summarizer(state:ResearchState):
    
    chunks=state['chunks']
    combined = "\n\n".join([chunk['chunk_text'] for chunk in chunks])
    combined = combined[:40000]

    prompt = f"""You are a research paper analyst. You will be given the full text of a research paper extracted from a PDF.
    Your task is to produce a structured summary with exactly three sections:
    **Contributions**
    What does this paper claim to contribute? What problem does it solve and why does it matter? List the key contributions clearly.
    **Methodology**
    How did the authors approach the problem? What techniques, models, datasets, or experimental setups did they use?
    **Results**
    What did they find? Include key metrics, comparisons, or outcomes. Be specific — do not just say "the model performed well."
    Paper text:
    {combined}
    Write the summary in clean, concise language. Do not add any section beyond the three above."""

    response=llm.invoke(prompt)
    summary=response.content

    return {'summary':summary}