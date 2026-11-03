from typing import Any

from pydantic import Field, model_validator

from base.models.view_models import BaseModel
from base.services.configuration import settings


class SendChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_configured_limit(self) -> "SendChatRequest":
        if len(self.content) > settings.max_chat_input_chars:
            raise ValueError(
                f"content must be at most {settings.max_chat_input_chars} characters"
            )
        return self


class SendChatResponse(BaseModel):
    content: str


class ChatMessageView(BaseModel):
    role: str
    content: str | None = None
    sequence: int
    tool_call_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ListChatResponse(BaseModel):
    messages: list[ChatMessageView]
