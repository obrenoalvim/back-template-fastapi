import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class NoteResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class NoteWithOwnerResponse(BaseModel):
    id: uuid.UUID
    title: str
    owner_email: str = Field(serialization_alias="ownerEmail")

    model_config = {"from_attributes": True, "populate_by_name": True}
