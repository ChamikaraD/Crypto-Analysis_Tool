from typing import List

from pydantic import BaseModel ,Field


class CryptoAnalysisRequests(BaseModel):
    coins :List[str] = Field(...,description ="Provide the list of coins to be analized")