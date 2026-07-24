from pydantic import BaseModel, Field
from datetime import datetime
from typing import List


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ConversationWithMessages(ConversationOut):
    messages: List[MessageOut] = []


class ChatRequest(BaseModel):
    # Size cap: prevents cost/DoS abuse of the LLM path with megabyte "messages".
    # 8k chars comfortably covers a long drafting brief.
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = None   # None = start new conversation
