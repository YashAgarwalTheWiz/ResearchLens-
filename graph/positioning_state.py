from typing import TypedDict, List


class PositioningState(TypedDict, total=False):
    mode: str               # "paper" (uploaded PDF) or "idea" (just a text description)
    extracted: dict         # our paper's facts from extractor.py (paper mode)
    idea_text: str          # the user's idea (idea mode)
    our_text: str           # the text we use to describe "our work" for search + ranking
    our_year: int
    search_queries: List[str]
    self_paper_id: str      # our paper's Semantic Scholar ID, if it's indexed
    related_papers: List[dict]
    related_facts: List[dict]
    coverage: List[dict]
    analysis: dict
    positioning: dict       # the final, verified result that we save and show
    error: str