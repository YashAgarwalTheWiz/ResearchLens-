from typing import List, Literal
from pydantic import BaseModel


# ---------- step 1: search queries ----------
class SearchQueriesOut(BaseModel):
    queries: List[str]


# ---------- step 2: facts about each related paper, from its abstract ----------
class RelatedFactsRow(BaseModel):
    ref: str               # "P1", "P2", ... — short labels are easier for the LLM than long S2 IDs
    task: str
    method: str
    datasets: List[str]
    metrics: List[str]
    key_result: str


class RelatedFactsOut(BaseModel):
    papers: List[RelatedFactsRow]


# ---------- step 3: where our paper stands ----------
class ContributionCheck(BaseModel):
    claim: str                                        # one contribution of OUR paper
    closest_refs: List[str]                           # e.g. ["P3", "P7"]
    how_it_differs: str
    overlap: Literal["low", "partial", "high"]


class GapItem(BaseModel):
    gap: str
    refs: List[str]


class PositioningOut(BaseModel):
    summary: str                     # 2-3 sentences, cites papers inline like [P3]
    contributions: List[ContributionCheck]
    gaps: List[GapItem]