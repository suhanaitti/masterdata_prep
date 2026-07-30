import type {
  AgentEvent, MappingView, MasterFile, MasterFileDetail, RejectionLogEntry, RunStatus, Side, UploadResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // response wasn't JSON - keep statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function listSheets(file: File): Promise<{ sheet_names: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/masters/list-sheets`, { method: "POST", body: form });
  return handle(res);
}

export async function uploadMasterFile(
  file: File, side: Side, sheetName?: string,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("side", side);
  if (sheetName) form.append("sheet_name", sheetName);
  const res = await fetch(`${API_BASE}/api/masters/upload`, { method: "POST", body: form });
  return handle(res);
}

export async function confirmMasterType(
  masterFileId: number, confirmedMasterType: string,
): Promise<MasterFileDetail> {
  const res = await fetch(`${API_BASE}/api/masters/${masterFileId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_master_type: confirmedMasterType }),
  });
  return handle(res);
}

export async function listMasterFiles(): Promise<MasterFile[]> {
  const res = await fetch(`${API_BASE}/api/masters`, { cache: "no-store" });
  return handle(res);
}

export async function getMasterFile(id: number | string): Promise<MasterFileDetail> {
  const res = await fetch(`${API_BASE}/api/masters/${id}`, { cache: "no-store" });
  return handle(res);
}

export async function deleteMasterFile(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/masters/${id}`, { method: "DELETE" });
  return handle(res);
}

export async function getMappingView(sourceFileId: number, destinationFileId: number): Promise<MappingView> {
  const res = await fetch(
    `${API_BASE}/api/field-mappings?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}`,
    { cache: "no-store" },
  );
  return handle(res);
}

export async function startMappingRun(sourceFileId: number, destinationFileId: number): Promise<RunStatus> {
  const res = await fetch(
    `${API_BASE}/api/field-mappings/run/start?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}`,
    { method: "POST" },
  );
  return handle(res);
}

export async function getRunStatus(sourceFileId: number, destinationFileId: number): Promise<RunStatus> {
  const res = await fetch(
    `${API_BASE}/api/field-mappings/run/status?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}`,
    { cache: "no-store" },
  );
  return handle(res);
}

export async function stopMappingRun(sourceFileId: number, destinationFileId: number): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/field-mappings/run/stop?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}`,
    { method: "POST" },
  );
  return handle(res);
}

export async function acceptFieldMapping(mappingId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/field-mappings/${mappingId}/accept`, { method: "POST" });
  return handle(res);
}

export async function rejectFieldMapping(mappingId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/field-mappings/${mappingId}/reject`, { method: "POST" });
  return handle(res);
}

export async function getRejectionLog(sourceFileId: number, destinationFileId: number): Promise<RejectionLogEntry[]> {
  const res = await fetch(
    `${API_BASE}/api/field-mappings/rejections?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}`,
    { cache: "no-store" },
  );
  return handle(res);
}

export async function restoreRejection(rejectionId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/field-mappings/rejections/${rejectionId}/restore`, { method: "POST" });
  return handle(res);
}

export type ExportFormat = "xlsx" | "csv" | "json";
export type ExportDataset = "suggestions" | "approved" | "all";

export function exportMappingsUrl(
  sourceFileId: number, destinationFileId: number,
  format: ExportFormat = "xlsx", dataset: ExportDataset = "suggestions",
): string {
  return `${API_BASE}/api/field-mappings/export?source_file_id=${sourceFileId}&destination_file_id=${destinationFileId}&format=${format}&dataset=${dataset}`;
}

export async function listEvents(params: {
  sourceFileId?: number; destinationFileId?: number; eventType?: string; limit?: number;
} = {}): Promise<AgentEvent[]> {
  const qs = new URLSearchParams();
  if (params.sourceFileId != null) qs.set("source_file_id", String(params.sourceFileId));
  if (params.destinationFileId != null) qs.set("destination_file_id", String(params.destinationFileId));
  if (params.eventType) qs.set("event_type", params.eventType);
  if (params.limit != null) qs.set("limit", String(params.limit));
  const res = await fetch(`${API_BASE}/api/events?${qs.toString()}`, { cache: "no-store" });
  return handle(res);
}

export { MASTER_TYPES } from "./types";
