"""Rich import HTTP envelopes; trusted identities and actor are server-owned."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel

from api.swim_program_contract import SwimProgramSummaryV2
from models.swim_import import SourceAcknowledgement
from models.swim_program_v2 import SwimProgramDocumentV2


class SwimImportDraftResponse(BaseModel):
    import_id: UUID
    program_id: UUID
    source_text: str
    source_sha256: str
    source_label: str | None
    source_week_label: str | None
    revision: int
    document: SwimProgramDocumentV2 | None
    summary: SwimProgramSummaryV2 | None
    acknowledgements: list[SourceAcknowledgement]
    fingerprint: str
    actor: Literal["user", "coach"]
    updated_at: str


class SwimImportListResponse(BaseModel):
    items: list[SwimImportDraftResponse]


class SwimImportPreviewResponse(BaseModel):
    preview_id: UUID
    base_revision: int
    document: SwimProgramDocumentV2
    summary: SwimProgramSummaryV2
    fingerprint: str
    expires_at: str
    import_id: UUID
    draft_revision: int
