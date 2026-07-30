from typing import Optional

from pydantic import BaseModel


class MappingFieldOut(BaseModel):
    id: int
    column_name: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    length: Optional[int] = None
    is_primary_key: bool = False
    is_business_identifier: bool = False


class FieldMappingPairOut(BaseModel):
    mapping_id: int
    mapping_type: str
    status: str
    confidence: Optional[float] = None
    match_basis: Optional[str] = None
    remarks: Optional[str] = None
    source: MappingFieldOut
    destination: MappingFieldOut


class MappingViewOut(BaseModel):
    matches: list[FieldMappingPairOut]
    ai_suggestions: list[FieldMappingPairOut]
    unmapped_source: list[MappingFieldOut]
    unmapped_destination: list[MappingFieldOut]


class RunStatusOut(BaseModel):
    status: str  # "idle" | "running" | "done" | "stopped" | "error"
    batches_done: int = 0
    total_batches: int = 0
    new_suggestions: int = 0
    failed_batches: list[int] = []
    error: Optional[str] = None


class ManualMapIn(BaseModel):
    source_field_id: int
    destination_field_id: int


class RejectionLogEntryOut(BaseModel):
    id: int
    confidence_score: Optional[float] = None
    rejected_at: str
    source: MappingFieldOut
    destination: MappingFieldOut
