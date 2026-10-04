"""Closed SQL request and bounded exact analytical response models."""
from datetime import date, datetime
import re
from typing import Literal
from pydantic import Field, field_validator, model_validator
from trinity.auth.schemas import StrictModel, Publication


class QueryRequest(StrictModel):
    """Accept one nonblank SQL string within the independent UTF-8 byte bound."""
    sql: str = Field(min_length=1,max_length=16384,repr=False)

    @field_validator('sql')
    @classmethod
    def bounded_sql(cls,value):
        if not value.strip() or len(value.encode('utf-8'))>16384:raise ValueError('Invalid SQL length')
        return value


class QueryColumn(StrictModel):
    """Preserve public column order, labels, types, nullability and units."""
    name: str = Field(min_length=1,max_length=128)
    type: Literal['string','date','timestamp','decimal','integer','boolean']
    nullable: bool
    unit: Literal['MW','percent'] | None


class QueryResponse(StrictModel):
    """Reject inconsistent or lossy cells before successful HTTP headers."""
    publication: Publication
    columns: list[QueryColumn] = Field(min_length=1,max_length=128)
    rows: list[list[str | bool | None]] = Field(max_length=1000,repr=False)
    returned_rows: int = Field(ge=0,le=1000)
    truncated: bool
    execution_ms: int = Field(ge=0)
    diagnostics: list = Field(max_length=0)

    @model_validator(mode='after')
    def exact_cells(self):
        if self.returned_rows!=len(self.rows) or self.truncated and self.returned_rows!=1000:raise ValueError('Invalid row count')
        for row in self.rows:
            if len(row)!=len(self.columns):raise ValueError('Invalid row shape')
            for value,column in zip(row,self.columns):
                if value is None:
                    if not column.nullable:raise ValueError('Invalid null')
                    continue
                if column.type=='boolean':
                    if type(value) is not bool:raise ValueError('Invalid boolean')
                elif type(value) is not str:raise ValueError('Invalid scalar')
                elif column.type=='integer' and re.fullmatch(r'-?[0-9]+',value) is None:raise ValueError('Invalid integer')
                elif column.type=='decimal' and re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',value) is None:raise ValueError('Invalid decimal')
                elif column.type=='date':date.fromisoformat(value)
                elif column.type=='timestamp':datetime.fromisoformat(value)
        return self
