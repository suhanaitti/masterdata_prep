export type Side = "source" | "destination";

export type MasterType =
  | "Customer"
  | "Vendor"
  | "Product"
  | "Bank"
  | "GL Mapping"
  | "Transaction Type"
  | "Payment Terms";

export interface MasterTypeCandidate {
  master_type: MasterType;
  confidence: number;
}

export interface FieldMetadata {
  column_name: string;
  ai_description: string | null;
  business_category: string | null;
  data_type: string | null;
  estimated_length: number | null;
  is_mandatory: boolean;
  is_primary_key: boolean;
  is_business_identifier: boolean;
  confidence_score: number | null;
  ai_remarks: string | null;
}

export interface ConsolidationConflict {
  column_name: string;
  issue: string;
  resolution: string;
}

export interface MasterFile {
  id: number;
  filename: string;
  sheet_name: string | null;
  side: Side;
  detected_master_type: MasterType | null;
  detection_confidence: number | null;
  confirmed_master_type: MasterType | null;
  status: "pending_confirmation" | "confirmed" | "rejected";
  row_count: number | null;
  column_count: number | null;
  // Only populated for wide files that needed more than one metadata-generation
  // chunk - see metadata_generator.consolidate_metadata(). Empty/null for a
  // single-chunk file, which has nothing to reconcile.
  business_purpose: string | null;
  consolidation_conflicts: ConsolidationConflict[];
  uploaded_at: string;
  confirmed_at: string | null;
}

export interface UploadResult {
  master_file: MasterFile;
  needs_confirmation: boolean;
  reasoning: string | null;
  candidates: MasterTypeCandidate[];
  possible_master_types: MasterType[];
  fields: FieldMetadata[];
}

export interface MasterFileDetail {
  master_file: MasterFile;
  fields: FieldMetadata[];
}

export const MASTER_TYPES: MasterType[] = [
  "Customer", "Vendor", "Product", "Bank", "GL Mapping", "Transaction Type", "Payment Terms",
];

export interface MappingField {
  id: number;
  column_name: string;
  description: string | null;
  data_type: string | null;
  length: number | null;
  is_primary_key: boolean;
  is_business_identifier: boolean;
}

export interface FieldMappingPair {
  mapping_id: number;
  mapping_type: "ai_suggested" | "manual";
  status: "suggested" | "approved";
  confidence: number | null;
  match_basis: string | null;
  remarks: string | null;
  source: MappingField;
  destination: MappingField;
}

export interface MappingView {
  matches: FieldMappingPair[];
  ai_suggestions: FieldMappingPair[];
  unmapped_source: MappingField[];
  unmapped_destination: MappingField[];
}

export interface RejectionLogEntry {
  id: number;
  confidence_score: number | null;
  rejected_at: string;
  source: MappingField;
  destination: MappingField;
}

export interface RunStatus {
  status: "idle" | "running" | "done" | "stopped" | "error";
  batches_done: number;
  total_batches: number;
  new_suggestions: number;
  failed_batches: number[];
  error: string | null;
}

export interface AgentEvent {
  id: number;
  event_type: string;
  source_file_id: number | null;
  destination_file_id: number | null;
  agent: string | null;
  status: "success" | "failed";
  duration_ms: number | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}
