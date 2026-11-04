from typing import List
from pydantic import BaseModel


class ParsedRef(BaseModel):
    title: str
    first_author: str     # surname of the first author, e.g. "He"
    year: str             # as written, e.g. "2016" ("" if none)


class ParsedRefsOut(BaseModel):
    references: List[ParsedRef]