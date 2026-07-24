from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentCreate(BaseModel):
    filename: str
    file_path: str
    notes: Optional[str] = None
    case_id: int


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_path: str
    notes: Optional[str]
    case_id: int
    uploaded_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    id: int
    document_id: int
    version_no: int
    original_filename: str
    content_type: Optional[str]
    size_bytes: int
    sha256: Optional[str]
    uploaded_by: int
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}
