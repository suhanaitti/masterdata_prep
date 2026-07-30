"use client";

import { useRef, useState } from "react";
import { CheckCircle2, FileSpreadsheet, UploadCloud } from "lucide-react";
import ConfidencePill from "./ConfidencePill";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { confirmMasterType, listSheets, uploadMasterFile } from "../lib/api";
import { MASTER_TYPES, MasterType, Side, UploadResult } from "../lib/types";

// One independent upload+classify+confirm flow for a single file. Used once for the
// destination slot and N times for source slots - each file is its own backend upload
// (its own side, its own master_file_id), so there's no shared state needed beyond
// "how many source slots exist", which the parent (UploadPage) manages.
export default function UploadSlot({
  side, onRemove, showRemove,
}: {
  side: Side;
  onRemove?: () => void;
  showRemove: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [sheetName, setSheetName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [chosenType, setChosenType] = useState<MasterType>(MASTER_TYPES[0]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(f: File | null) {
    setFile(f);
    setResult(null);
    setError(null);
    setSheetNames([]);
    setSheetName("");
    if (!f) return;
    if (/\.(xlsx|xls)$/i.test(f.name)) {
      try {
        const { sheet_names } = await listSheets(f);
        if (sheet_names.length > 1) {
          // Wide workbook - don't auto-upload, let the user pick which sheet has the
          // field list first (the Upload button below only appears once a file is
          // selected but still needs a sheet choice).
          setSheetNames(sheet_names);
          setSheetName(sheet_names[0]);
          return;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return;
      }
    }
    await onUpload(f, "");
  }

  async function onUpload(f: File, sheet: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await uploadMasterFile(f, side, sheet || undefined);
      setResult(res);
      if (res.master_file.detected_master_type) setChosenType(res.master_file.detected_master_type);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await confirmMasterType(result.master_file.id, chosenType);
      setResult({ ...result, master_file: detail.master_file, needs_confirmation: false, fields: detail.fields });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function resetSlot() {
    setFile(null);
    setResult(null);
    setError(null);
    setSheetNames([]);
    setSheetName("");
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }

  const sideLabel = side === "source" ? "Source" : "Destination";
  const isConfirmed = !!result && !result.needs_confirmation;
  const uploadedDate = result?.master_file.uploaded_at
    ? new Date(result.master_file.uploaded_at).toLocaleDateString()
    : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{sideLabel} Dataset</CardTitle>
          {showRemove && (
            <Button variant="ghost" size="sm" onClick={onRemove} className="text-destructive">Remove slot</Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isConfirmed && result && (
          <>
            <Badge variant="success" className="gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Uploaded Successfully
            </Badge>

            <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="h-4 w-4 text-primary shrink-0" />
                <span className="text-sm font-medium truncate">{result.master_file.filename}</span>
              </div>
              <dl className="grid grid-cols-2 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Master Type</dt>
                <dd className="text-right">
                  {result.master_file.confirmed_master_type}{" "}
                  <ConfidencePill value={result.master_file.detection_confidence} />
                </dd>
                <dt className="text-muted-foreground">Total Fields</dt>
                <dd className="text-right">{result.fields.length}</dd>
                <dt className="text-muted-foreground">Upload Date</dt>
                <dd className="text-right">{uploadedDate}</dd>
              </dl>
            </div>

            <Collapsible>
              <CollapsibleTrigger asChild>
                <Button variant="secondary" size="sm">View Fields</Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-3">
                {result.master_file.business_purpose && (
                  <p className="text-sm text-muted-foreground italic mb-2">{result.master_file.business_purpose}</p>
                )}
                {result.master_file.consolidation_conflicts.length > 0 && (
                  <div className="mb-2 rounded-md bg-warning/10 px-3 py-2 text-sm">
                    <p className="font-medium text-warning mb-1">
                      Conflicts resolved across chunks ({result.master_file.consolidation_conflicts.length}):
                    </p>
                    <ul className="list-disc list-inside">
                      {result.master_file.consolidation_conflicts.map((c) => (
                        <li key={c.column_name}>
                          <span className="font-medium">{c.column_name}</span>: {c.issue} — {c.resolution}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="bg-muted/60">
                        <th className="text-left px-2 py-1.5 border-b border-border">Column</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Description</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Type</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Length</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Mandatory</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Key</th>
                        <th className="text-left px-2 py-1.5 border-b border-border">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.fields.map((f) => (
                        <tr key={f.column_name}>
                          <td className="px-2 py-1.5 border-b border-border">{f.column_name}</td>
                          <td className="px-2 py-1.5 border-b border-border">{f.ai_description}</td>
                          <td className="px-2 py-1.5 border-b border-border">{f.data_type}</td>
                          <td className="px-2 py-1.5 border-b border-border">{f.estimated_length ?? "—"}</td>
                          <td className="px-2 py-1.5 border-b border-border">{f.is_mandatory ? "Yes" : "No"}</td>
                          <td className="px-2 py-1.5 border-b border-border">
                            {[f.is_primary_key && "PK", f.is_business_identifier && "Business ID"].filter(Boolean).join(", ") || "—"}
                          </td>
                          <td className="px-2 py-1.5 border-b border-border"><ConfidencePill value={f.confidence_score} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CollapsibleContent>
            </Collapsible>

            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>Replace File</Button>
              <Button variant="secondary" size="sm" onClick={resetSlot} className="text-destructive">Remove</Button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
          </>
        )}

        {!isConfirmed && result?.needs_confirmation && (
          <div className="space-y-2">
            <p className="text-sm">
              <span className="font-medium">{result.master_file.filename}</span> — detected:{" "}
              <strong>{result.master_file.detected_master_type || "unknown"}</strong>{" "}
              <ConfidencePill value={result.master_file.detection_confidence} />
            </p>
            {result.candidates.length > 1 && (
              <p className="text-sm text-muted-foreground">
                Possible master:{" "}
                {result.candidates.map((c, i) => (
                  <span key={c.master_type}>
                    {i > 0 && ", "}
                    {c.master_type} ({c.confidence.toFixed(0)}%)
                  </span>
                ))}
              </p>
            )}
            {result.reasoning && <p className="text-sm text-muted-foreground">{result.reasoning}</p>}
            <p className="text-sm text-warning">Confidence too low — please confirm the correct master type.</p>
            <div className="flex gap-2">
              <select
                value={chosenType}
                onChange={(e) => setChosenType(e.target.value as MasterType)}
                className="h-10 rounded-md border border-input bg-white px-2 text-sm"
              >
                {result.possible_master_types.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <Button onClick={onConfirm} disabled={busy}>Confirm & Generate Metadata</Button>
            </div>
          </div>
        )}

        {!result && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
              dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"
            }`}
          >
            <UploadCloud className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">Drag &amp; Drop</p>
            <p className="text-xs text-muted-foreground">or</p>
            <Button variant="secondary" size="sm" disabled={busy}>
              {busy ? "Uploading..." : "Browse File"}
            </Button>
            <p className="text-xs text-muted-foreground mt-2">Supported: Excel, CSV, XML, JSON</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
          </div>
        )}

        {sheetNames.length > 1 && !result && (
          <div className="flex items-center gap-2">
            <label className="text-sm">This file has multiple sheets — which has the field list?</label>
            <select
              value={sheetName}
              onChange={(e) => setSheetName(e.target.value)}
              className="h-9 rounded-md border border-input bg-white px-2 text-sm"
            >
              {sheetNames.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <Button size="sm" disabled={!file || busy} onClick={() => file && onUpload(file, sheetName)}>
              {busy ? "Uploading..." : "Upload"}
            </Button>
          </div>
        )}

        {error && <div className="rounded-md bg-destructive/10 text-destructive text-sm px-3 py-2">{error}</div>}
      </CardContent>
    </Card>
  );
}
