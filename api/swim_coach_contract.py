"""Explicit source-bound Coach request and authoritative import SSE events."""

from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, TypeAdapter, field_validator
from models.swim_program import DocumentPart


class SwimCoachTurnRequest(DocumentPart):
    message: Annotated[StrictStr, Field(min_length=1, max_length=10000)]
    import_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=0)]
    request_id: UUID
    chat_id: Annotated[StrictStr, Field(pattern=r"^[0-9a-zA-Z_-]{1,64}$")] | None = None
    provider: Annotated[StrictStr, Field(min_length=1, max_length=40)] | None = None

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("nonblank message required")
        return value


class SwimCoachMeta(DocumentPart):
    type: Literal["meta"]
    chat_id: str
    import_id: UUID


class SwimCoachToolEvent(DocumentPart):
    type: Literal["tool_call"]
    name: str
    tool_name: Literal[
        "get_swim_import",
        "search_swim_exercises",
        "get_swim_exercise",
        "get_swim_program",
        "parse_swim_import",
        "patch_swim_import",
        "ask_swim_import_question",
        "unsupported",
    ]
    status: Literal["done", "error"]
    native: Literal[True]


class SwimCoachDraftEvent(DocumentPart):
    type: Literal["swim_import"]
    import_id: UUID
    revision: int
    status: Literal["draft", "unparsed", "error"]
    code: str | None
    library_saved: Literal[False]


class SwimCoachToken(DocumentPart):
    type: Literal["token"]
    content: str


class SwimCoachDone(DocumentPart):
    type: Literal["done"]
    chat_id: str
    import_id: UUID
    revision: int


SwimCoachEvent = Annotated[
    Union[
        SwimCoachMeta,
        SwimCoachToolEvent,
        SwimCoachDraftEvent,
        SwimCoachToken,
        SwimCoachDone,
    ],
    Field(discriminator="type"),
]
SWIM_COACH_EVENT = TypeAdapter(SwimCoachEvent)
