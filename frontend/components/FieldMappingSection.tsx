"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Download, Play, Square } from "lucide-react";
import ConfidencePill from "./ConfidencePill";
import FiltersBar, { ConfidenceFilter, StatusFilter } from "./FiltersBar";
import StatsRow from "./StatsRow";
import ProcessingTimeline, { StepStatus } from "./ProcessingTimeline";
import MappingSidebar from "./MappingSidebar";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Slider } from "./ui/slider";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import {
  acceptFieldMapping, exportMappingsUrl, getMappingView, getRejectionLog, getRunStatus, listMasterFiles,
  rejectFieldMapping, restoreRejection, startMappingRun, stopMappingRun,
} from "../lib/api";
import { FieldMappingPair, MasterFile, RejectionLogEntry, RunStatus } from "../lib/types";

const POLL_INTERVAL_MS = 1500;

export default function FieldMappingSection() {
  const [files, setFiles] = useState<MasterFile[]>([]);
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [destId, setDestId] = useState<number | null>(null);
  const [view, setView] = useState<Awaited<ReturnType<typeof getMappingView>> | null>(null);
  const [rejections, setRejections] = useState<RejectionLogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runInfo, setRunInfo] = useState<string | null>(null);
  const [bulkThreshold, setBulkThreshold] = useState(70);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [search, setSearch] = useState("");
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    listMasterFiles().then((all) => setFiles(all.filter((f) => f.status === "confirmed")));
  }, []);

  const sourceOptions = files.filter((f) => f.side === "source");
  const destOptions = files.filter((f) => f.side === "destination");
  const sourceFile = files.find((f) => f.id === sourceId) || null;
  const destFile = files.find((f) => f.id === destId) || null;

  async function refreshView() {
    if (!sourceId || !destId) return;
    try {
      setView(await getMappingView(sourceId, destId));
      setRejections(await getRejectionLog(sourceId, destId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    stopPolling();
    setView(null);
    setRejections([]);
    setRunInfo(null);
    setRunStatus(null);
    if (sourceId && destId) refreshView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId, destId]);

  function stopPolling() {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }

  async function pollStatus(srcId: number, dstId: number) {
    try {
      const s = await getRunStatus(srcId, dstId);
      setRunStatus(s);
      if (s.status === "running") {
        pollRef.current = setTimeout(() => pollStatus(srcId, dstId), POLL_INTERVAL_MS);
        return;
      }
      stopPolling();
      if (s.status === "error") {
        setError(s.error || "AI field mapping failed.");
      } else if (s.status === "stopped") {
        setRunInfo(
          `Stopped at your request - completed ${s.batches_done} of ${s.total_batches} batch(es), ` +
          `found ${s.new_suggestions} suggestion(s) so far. Everything found is saved - Run AI Mapping again to continue.`,
        );
      } else if (s.new_suggestions > 0) {
        setRunInfo(`Found ${s.new_suggestions} new suggestion(s).`);
      } else {
        setRunInfo("No new matches found - resolve the rest manually, or nothing left to map.");
      }
      setLastRunAt(new Date());
      await refreshView();
    } catch (err) {
      stopPolling();
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onRunMapping() {
    if (!sourceId || !destId) return;
    setError(null);
    setRunInfo(null);
    try {
      await startMappingRun(sourceId, destId);
      pollStatus(sourceId, destId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onStopMapping() {
    if (!sourceId || !destId) return;
    try {
      await stopMappingRun(sourceId, destId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => stopPolling, []);

  const isRunning = runStatus?.status === "running";

  async function onAccept(mappingId: number) {
    await acceptFieldMapping(mappingId);
    refreshView();
  }

  async function onReject(mappingId: number) {
    await rejectFieldMapping(mappingId);
    refreshView();
  }

  async function onRestore(rejectionId: number) {
    await restoreRejection(rejectionId);
    refreshView();
  }

  const matchesSearch = (p: FieldMappingPair) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return p.source.column_name.toLowerCase().includes(q) || p.destination.column_name.toLowerCase().includes(q);
  };
  const matchesConfidence = (p: FieldMappingPair) => {
    const c = p.confidence ?? 0;
    if (confidenceFilter === "high") return c >= 80;
    if (confidenceFilter === "medium") return c >= 65 && c < 80;
    if (confidenceFilter === "low") return c < 65;
    return true;
  };

  const visibleSuggestions = useMemo(
    () => (view ? view.ai_suggestions.filter((p) => matchesSearch(p) && matchesConfidence(p)) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [view, search, confidenceFilter],
  );
  const visibleMatches = useMemo(
    () => (view ? view.matches.filter(matchesSearch) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [view, search],
  );

  const showSuggestions = statusFilter === "all" || statusFilter === "pending";
  const showMatches = statusFilter === "all" || statusFilter === "mapped";
  const showRejected = statusFilter === "all" || statusFilter === "rejected";

  const above = visibleSuggestions.filter((p) => (p.confidence ?? 0) >= bulkThreshold);
  const below = visibleSuggestions.filter((p) => (p.confidence ?? 0) < bulkThreshold);

  async function onBulkAccept() {
    setBusy(true);
    try {
      await Promise.all(visibleSuggestions.map((p) => acceptFieldMapping(p.mapping_id)));
      await refreshView();
    } finally {
      setBusy(false);
    }
  }

  async function onBulkReject() {
    setBusy(true);
    try {
      await Promise.all(visibleSuggestions.map((p) => rejectFieldMapping(p.mapping_id)));
      await refreshView();
    } finally {
      setBusy(false);
    }
  }

  const totalSourceFields = view ? view.matches.length + view.ai_suggestions.length + view.unmapped_source.length : 0;

  const high = visibleSuggestions.filter((p) => (p.confidence ?? 0) >= 80);
  const needsReview = visibleSuggestions.filter((p) => (p.confidence ?? 0) >= 65 && (p.confidence ?? 0) < 80);
  const likelyNoMatch = visibleSuggestions.filter((p) => (p.confidence ?? 0) < 65);

  const timelineSteps: { label: string; status: StepStatus }[] = [
    { label: "Upload", status: sourceFile && destFile ? "done" : sourceFile || destFile ? "active" : "pending" },
    { label: "Master Classification", status: sourceFile && destFile ? "done" : "pending" },
    { label: "Metadata Generation", status: sourceFile && destFile ? "done" : "pending" },
    {
      label: "AI Mapping",
      status: isRunning ? "active" : view && (view.matches.length || view.ai_suggestions.length) ? "done" : "pending",
    },
    {
      label: "Human Review",
      status: view && view.ai_suggestions.length === 0 && view.matches.length > 0
        ? "done"
        : view && view.ai_suggestions.length > 0 ? "active" : "pending",
    },
    {
      label: "Completed",
      status: view && totalSourceFields > 0 && view.ai_suggestions.length === 0 && view.unmapped_source.length === 0
        ? "done"
        : "pending",
    },
  ];

  return (
    <section className="mt-10 space-y-6">
      <div className="flex flex-wrap gap-4">
        <select
          value={sourceId ?? ""}
          onChange={(e) => setSourceId(e.target.value ? Number(e.target.value) : null)}
          className="h-10 rounded-md border border-input bg-white px-3 text-sm shadow-soft"
        >
          <option value="">Choose source file...</option>
          {sourceOptions.map((f) => (
            <option key={f.id} value={f.id}>{f.filename} ({f.confirmed_master_type})</option>
          ))}
        </select>
        <select
          value={destId ?? ""}
          onChange={(e) => setDestId(e.target.value ? Number(e.target.value) : null)}
          className="h-10 rounded-md border border-input bg-white px-3 text-sm shadow-soft"
        >
          <option value="">Choose destination file...</option>
          {destOptions.map((f) => (
            <option key={f.id} value={f.id}>{f.filename} ({f.confirmed_master_type})</option>
          ))}
        </select>
      </div>

      {view && (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 items-start">
          <div className="xl:col-span-3 space-y-6">
            <StatsRow
              mapped={view.matches.length}
              pending={view.ai_suggestions.length}
              unmappedSource={view.unmapped_source.length}
              unmappedDestination={view.unmapped_destination.length}
              totalSource={totalSourceFields}
            />

            <Card>
              <CardContent className="p-5 flex flex-wrap items-center gap-3">
                {!isRunning ? (
                  <Button onClick={onRunMapping} disabled={!sourceId || !destId}>
                    <Play className="h-4 w-4" /> Run AI Mapping
                  </Button>
                ) : (
                  <Button onClick={onStopMapping} variant="destructive">
                    <Square className="h-4 w-4" /> Stop Mapping
                  </Button>
                )}
                <Button variant="secondary" asChild disabled={!view.matches.length}>
                  <a href={sourceId && destId ? exportMappingsUrl(sourceId, destId, "xlsx", "approved") : "#"}>
                    <Download className="h-4 w-4" /> Export Results
                  </a>
                </Button>
                <Button variant="secondary" asChild disabled={!view.ai_suggestions.length}>
                  <a href={sourceId && destId ? exportMappingsUrl(sourceId, destId, "xlsx", "suggestions") : "#"}>
                    <Download className="h-4 w-4" /> Download Excel
                  </a>
                </Button>

                {isRunning && runStatus && (
                  <span className="text-sm text-muted-foreground">
                    {runStatus.total_batches > 0
                      ? `Batch ${runStatus.batches_done} / ${runStatus.total_batches} complete`
                      : "Starting..."}
                  </span>
                )}
              </CardContent>
            </Card>

            {error && <div className="rounded-md bg-destructive/10 text-destructive text-sm px-3 py-2">{error}</div>}
            {runInfo && <div className="rounded-md bg-success/10 text-success text-sm px-3 py-2">{runInfo}</div>}

            <FiltersBar
              search={search} onSearchChange={setSearch}
              confidence={confidenceFilter} onConfidenceChange={setConfidenceFilter}
              status={statusFilter} onStatusChange={setStatusFilter}
            />

            {showSuggestions && visibleSuggestions.length > 0 && (
              <Card>
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <CardTitle>AI Suggestions Awaiting Review</CardTitle>
                  <Button variant="secondary" size="sm" asChild>
                    <a href={sourceId && destId ? exportMappingsUrl(sourceId, destId, "xlsx", "all") : "#"}>
                      <Download className="h-4 w-4" /> Download Mapping Results
                    </a>
                  </Button>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-xs text-muted-foreground -mt-2">
                    Downloads Source Field / Destination Field / Confidence / AI Reason / Status for every mapping AI
                    has proposed so far - both pending and already-approved - so you can review or share it
                    regardless of where human approval stands.
                  </p>
                  <div className="flex items-center gap-3 flex-wrap">
                    <Button variant="secondary" size="sm" onClick={onBulkAccept} disabled={busy || above.length === 0}>
                      Accept All ({above.length})
                    </Button>
                    <Button variant="secondary" size="sm" onClick={onBulkReject} disabled={busy || below.length === 0}>
                      Reject All ({below.length})
                    </Button>
                    <div className="flex items-center gap-3 flex-1 min-w-[180px]">
                      <Slider
                        value={[bulkThreshold]}
                        onValueChange={([v]) => setBulkThreshold(v)}
                        min={0} max={100} step={1}
                        className="flex-1"
                      />
                      <span className="text-sm font-medium w-12 text-right">{bulkThreshold}%</span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    "Accept All" applies to fields at or above the slider threshold; "Reject All" to fields below it.
                  </p>

                  {high.length > 0 && (
                    <SuggestionGroup title={`High confidence (${high.length})`} pairs={high} onAccept={onAccept} onReject={onReject} />
                  )}
                  {needsReview.length > 0 && (
                    <SuggestionGroup title={`Needs review (${needsReview.length})`} pairs={needsReview} onAccept={onAccept} onReject={onReject} />
                  )}
                  {likelyNoMatch.length > 0 && (
                    <Collapsible>
                      <CollapsibleTrigger className="text-sm font-medium mb-2 flex items-center gap-1">
                        Likely no match ({likelyNoMatch.length})
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-3 pt-2">
                        {likelyNoMatch.map((p) => (
                          <SuggestionCard key={p.mapping_id} pair={p} onAccept={onAccept} onReject={onReject} />
                        ))}
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </CardContent>
              </Card>
            )}

            {showRejected && rejections.length > 0 && (
              <Card>
                <Collapsible>
                  <CollapsibleTrigger className="w-full text-left">
                    <CardHeader>
                      <CardTitle>Rejected Suggestions ({rejections.length})</CardTitle>
                    </CardHeader>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <CardContent className="space-y-2">
                      {rejections.map((r) => (
                        <div key={r.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                          <span className="text-sm">
                            <strong>{r.source.column_name}</strong> &rarr; <strong>{r.destination.column_name}</strong>{" "}
                            <ConfidencePill value={r.confidence_score} />
                          </span>
                          <Button size="sm" variant="secondary" onClick={() => onRestore(r.id)}>Restore</Button>
                        </div>
                      ))}
                    </CardContent>
                  </CollapsibleContent>
                </Collapsible>
              </Card>
            )}

            {showMatches && (
              <Card>
                <CardHeader>
                  <CardTitle>Confirmed Mappings ({visibleMatches.length})</CardTitle>
                </CardHeader>
                <CardContent>
                  {visibleMatches.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No confirmed mappings yet.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm border-collapse">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left px-2 py-2 font-medium text-muted-foreground">Source</th>
                            <th className="text-left px-2 py-2 font-medium text-muted-foreground">Destination</th>
                            <th className="text-left px-2 py-2 font-medium text-muted-foreground">Confidence</th>
                            <th className="text-left px-2 py-2 font-medium text-muted-foreground">Status</th>
                            <th className="text-left px-2 py-2 font-medium text-muted-foreground">Approved By</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleMatches.map((m) => (
                            <tr key={m.mapping_id} className="border-b border-border last:border-0">
                              <td className="px-2 py-2">{m.source.column_name}</td>
                              <td className="px-2 py-2">{m.destination.column_name}</td>
                              <td className="px-2 py-2"><ConfidencePill value={m.confidence} /></td>
                              <td className="px-2 py-2">
                                <Badge variant="success">Approved</Badge>
                              </td>
                              <td className="px-2 py-2 text-muted-foreground">
                                {m.mapping_type === "manual" ? "Manual" : "AI (reviewed)"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            <ProcessingTimeline steps={timelineSteps} />
          </div>

          <div className="xl:col-span-1">
            <MappingSidebar
              sourceFile={sourceFile}
              destFile={destFile}
              sourceFieldCount={totalSourceFields}
              destFieldCount={view.matches.length + view.unmapped_destination.length}
              lastRunAt={lastRunAt}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function SuggestionGroup({
  title, pairs, onAccept, onReject,
}: {
  title: string;
  pairs: FieldMappingPair[];
  onAccept: (id: number) => void;
  onReject: (id: number) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">{title}</p>
      {pairs.map((p) => (
        <SuggestionCard key={p.mapping_id} pair={p} onAccept={onAccept} onReject={onReject} />
      ))}
    </div>
  );
}

function confidenceBadgeVariant(v: number | null): "success" | "warning" | "destructive" {
  const c = v ?? 0;
  if (c >= 80) return "success";
  if (c >= 65) return "warning";
  return "destructive";
}

function SuggestionCard({
  pair, onAccept, onReject,
}: {
  pair: FieldMappingPair;
  onAccept: (id: number) => void;
  onReject: (id: number) => void;
}) {
  return (
    <div className="rounded-xl border border-border p-4 shadow-soft transition-shadow hover:shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-4 items-center">
          <FieldBlock
            columnName={pair.source.column_name}
            description={pair.source.description}
            dataType={pair.source.data_type}
            length={pair.source.length}
          />
          <span className="text-muted-foreground text-lg justify-self-center hidden sm:block">&darr;</span>
          <FieldBlock
            columnName={pair.destination.column_name}
            description={pair.destination.description}
            dataType={pair.destination.data_type}
            length={pair.destination.length}
          />
        </div>
        <Badge variant={confidenceBadgeVariant(pair.confidence)} className="shrink-0">
          {pair.confidence != null ? `${pair.confidence.toFixed(0)}%` : "—"}
        </Badge>
      </div>

      <ReasonChecklist pair={pair} />

      <div className="mt-3 flex gap-2">
        <Button size="sm" onClick={() => onAccept(pair.mapping_id)}>
          <CheckCircle2 className="h-4 w-4" /> Accept
        </Button>
        <Button size="sm" variant="secondary" onClick={() => onReject(pair.mapping_id)}>Reject</Button>
      </div>
    </div>
  );
}

function FieldBlock({
  columnName, description, dataType, length,
}: {
  columnName: string;
  description: string | null;
  dataType: string | null;
  length: number | null;
}) {
  return (
    <div>
      <p className="font-semibold text-sm">{columnName}</p>
      {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
      <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
        <span>{dataType || "—"}</span>
        {length != null && <span>Length {length}</span>}
      </div>
    </div>
  );
}

const INTERNAL_ID_MARKERS = ["RECID", "ROWID", "SYSID", "GUID", "UUID"];
const isInternalIdName = (name: string) => INTERNAL_ID_MARKERS.some((m) => name.toUpperCase().includes(m));

function ReasonChecklist({ pair }: { pair: FieldMappingPair }) {
  const lines: { icon: "check" | "warn" | "note"; text: string }[] = [];
  const { source: src, destination: dst } = pair;

  if (pair.match_basis === "Exact Name") {
    lines.push({ icon: "check", text: "Field names match exactly." });
  } else if (pair.match_basis === "Description" || pair.match_basis === "Description + Name") {
    lines.push({ icon: "check", text: "Business descriptions are highly similar." });
  }

  if (src.data_type && dst.data_type) {
    if (src.data_type.trim().toLowerCase() === dst.data_type.trim().toLowerCase()) {
      lines.push({ icon: "check", text: `Same datatype family (${src.data_type}).` });
    } else {
      lines.push({ icon: "warn", text: `Data types differ (${src.data_type} vs ${dst.data_type}).` });
    }
  } else {
    lines.push({ icon: "warn", text: "Data type could not be verified on one or both sides." });
  }

  if (src.length != null && dst.length != null) {
    if (src.length === dst.length) {
      lines.push({ icon: "check", text: "Field lengths match." });
    } else {
      lines.push({ icon: "warn", text: `Length differs slightly (${src.length} vs ${dst.length}).` });
    }
  }

  if (isInternalIdName(src.column_name) || isInternalIdName(dst.column_name)) {
    lines.push({
      icon: "warn",
      text: `Verify ${src.column_name} and ${dst.column_name} represent the SAME business identifier.`,
    });
  }

  if (pair.remarks) {
    lines.push({ icon: "note", text: `AI confidence based on: ${pair.remarks}` });
  }

  const iconChar = { check: "✓", warn: "⚠", note: "ℹ" };
  const iconClass = { check: "text-success", warn: "text-warning", note: "text-muted-foreground" };

  return (
    <div className="mt-3 space-y-1 border-t border-border pt-3">
      {lines.map((l, i) => (
        <p key={i} className="text-xs text-muted-foreground">
          <span className={`mr-1.5 font-semibold ${iconClass[l.icon]}`}>{iconChar[l.icon]}</span>
          {l.text}
        </p>
      ))}
    </div>
  );
}
