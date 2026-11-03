import re

from graph.state import ResearchState

REF = re.compile(r"\[S(\d+)\]")


def citation_builder(state: ResearchState) -> dict:
    """Grounding check done in CODE: keep only the excerpts the answer actually cites,
    and delete any [S9] the model invented (there were only 5 excerpts)."""
    docs = state.get('retrieved_docs', [])
    cited = []

    def check(match):
        n = int(match.group(1))
        if 1 <= n <= len(docs):
            if n not in cited:
                cited.append(n)
            return match.group(0)
        return ""                         # invented reference -> remove it

    answer = REF.sub(check, state.get('answer', ''))
    answer = re.sub(r"[ \t]+([.,;:])", r"\1", answer).replace("  ", " ").strip()   # tidy gaps left behind

    citations = [{
        'ref': f"S{n}",
        'chunk_text': docs[n - 1]['chunk_text'],
        'page_number': docs[n - 1]['page_number'],
        'chunk_index': docs[n - 1]['chunk_index'],
        'section': docs[n - 1].get('section', 'unknown'),
    } for n in cited]

    return {'answer': answer, 'citations': citations}