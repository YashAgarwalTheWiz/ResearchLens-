from typing import List
from pydantic import BaseModel

NOT_STATED = "not stated in paper"


# ---------- what we STORE: every value carries its proof ----------
class Evidence(BaseModel):
    chunk_index: int      # -1 means the evidence is a table
    page_number: int
    section: str
    quote: str


class Fact(BaseModel):    # your plan calls this "Field"; renamed to avoid clashing with pydantic.Field
    value: str
    evidence: List[Evidence]


class Score(BaseModel):
    """One reported number: e.g. top-1 accuracy on ImageNet = 96.4% (best baseline: VGG-16, 92.5%)."""
    metric: str
    dataset: str
    value: str
    baseline: str             # strongest method it was compared against ("" if none)
    baseline_value: str       # that method's number ("" if none or not verifiable)
    evidence: List[Evidence]


class ExtractedPaper(BaseModel):
    title: str
    authors: List[str]
    year: str
    problem: Fact
    core_idea: Fact
    method: Fact
    datasets: List[Fact]
    metrics: List[Fact]
    scores: List[Score] = []
    results: List[Fact]
    limitations: List[Fact]
    future_work: List[Fact]


# ---------- what the LLM RETURNS: no page numbers, we add those after checking the quote ----------
class RawFact(BaseModel):
    value: str
    quote: str


class RawScore(BaseModel):
    metric: str
    dataset: str
    value: str
    baseline: str
    baseline_value: str
    quote: str


class IdentityOut(BaseModel):
    title: str
    authors: List[str]
    year: str


class OverviewOut(BaseModel):
    problem: RawFact
    core_idea: RawFact


class MethodOut(BaseModel):
    method: RawFact


class DatasetsOut(BaseModel):
    datasets: List[RawFact]


class ResultsOut(BaseModel):
    metrics: List[RawFact]
    scores: List[RawScore]
    results: List[RawFact]


class ClosingOut(BaseModel):
    limitations: List[RawFact]
    future_work: List[RawFact]