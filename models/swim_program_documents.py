"""Version dispatch that preserves schema1 canonical bytes and derived data."""

from typing import Annotated, Any, Union
import hashlib

from pydantic import Discriminator, Tag, TypeAdapter

from models.swim_program import SwimProgramDocument, canonical_json, summarize_program
from models.swim_program_v2 import SwimProgramDocumentV2, summarize_program_v2


def _version(value: Any) -> int | None:
    version = (
        value.get("schema_version")
        if isinstance(value, dict)
        else getattr(value, "schema_version", None)
    )
    return version if type(version) is int else None


ProgramDocument = Annotated[
    Union[
        Annotated[SwimProgramDocument, Tag(1)], Annotated[SwimProgramDocumentV2, Tag(2)]
    ],
    Discriminator(_version),
]
PROGRAM_ADAPTER = TypeAdapter(ProgramDocument)


def validate_program_document(
    payload: Any,
) -> SwimProgramDocument | SwimProgramDocumentV2:
    return PROGRAM_ADAPTER.validate_python(payload)


def fingerprint_program(document: SwimProgramDocument | SwimProgramDocumentV2) -> str:
    return hashlib.sha256(
        canonical_json(document.model_dump(mode="json")).encode()
    ).hexdigest()


def summarize_document(
    document: SwimProgramDocument | SwimProgramDocumentV2,
) -> dict[str, Any]:
    return (
        summarize_program(document)
        if isinstance(document, SwimProgramDocument)
        else summarize_program_v2(document)
    )
