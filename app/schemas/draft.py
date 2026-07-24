from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DraftSaveRequest(BaseModel):
    # Size caps: a draft is a document, not a blob store (300k chars ≈ 100+ pages).
    document_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=300_000)
    case_id: Optional[int] = None


class DraftEdit(BaseModel):
    content: str = Field(min_length=1, max_length=300_000)
    title: Optional[str] = Field(default=None, max_length=300)


class DraftVersionOut(BaseModel):
    id: int
    version_no: int
    title: str
    content: str
    created_by: int
    created_at: Optional[datetime]
    model_config = {"from_attributes": True}


class DraftOut(BaseModel):
    id: int
    case_id: Optional[int]
    document_type: str
    title: str
    content: str
    status: str
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
