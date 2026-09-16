from typing import Optional
from pydantic import BaseModel, ConfigDict


class TeamResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
