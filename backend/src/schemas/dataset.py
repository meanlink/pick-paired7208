from pydantic import BaseModel, Field
class DatasetInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    source: str = Field(default='manual.json', max_length=200)
    records: list[dict] = Field(min_length=5, max_length=5000)
class CorrectInput(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    records: list[dict] = Field(min_length=5, max_length=5000)
class WithdrawInput(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    operators: list[str] = Field(min_length=1, max_length=500)
