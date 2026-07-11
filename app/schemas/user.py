import uuid

from pydantic import BaseModel, EmailStr


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str

    model_config = {"from_attributes": True}
