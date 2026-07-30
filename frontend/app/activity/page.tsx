"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { listEvents, listMasterFiles } from "../../lib/api";
import { AgentEvent, MasterFile } from "../../lib/types";

const selectClass =
  "h-10 rounded-md border border-input bg-white px-3 text-sm shadow-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const EVENT_TYPES = [
  "classification", "metadata_generation", "exact_name_match", "field_mapping_batch", "accept", "reject", "manual_map",
];

export default function ActivityPage() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [files, setFiles] = useState<MasterFile[]>([]);
  const [eventType, setEventType] = useState("");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listEvents({ eventType: eventType || undefined, limit: 200 })
      .then(setEvents)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    listMasterFiles().then(setFiles).catch(() => {});
  }, []);

  useEffect(refresh, [eventType]);

  const fileName = (id: number | null) => {
    if (id == null) return "—";
    return files.find((f) => f.id === id)?.filename ?? `#${id}`;
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Agent Activity Log</h1>
        <p className="text-muted-foreground mt-1">
          Every AI call (classification, metadata generation, field mapping) and human decision (accept/reject/manual
          correction) - which agent did it, what happened, how long it took.
        </p>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <select value={eventType} onChange={(e) => setEventType(e.target.value)} className={selectClass}>
          <option value="">All event types</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {error && <div className="rounded-md bg-destructive/10 text-destructive text-sm px-3 py-2 mb-4">{error}</div>}

      <Card>
        <CardHeader>
          <CardTitle>Events ({events.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Time</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Event</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Agent</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Source File</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Destination File</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Duration</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Status</th>
                    <th className="text-left px-2 py-2 font-medium text-muted-foreground">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} className="border-b border-border last:border-0 align-top">
                      <td className="px-2 py-2 whitespace-nowrap text-muted-foreground">
                        {new Date(e.created_at).toLocaleString()}
                      </td>
                      <td className="px-2 py-2 font-medium">{e.event_type}</td>
                      <td className="px-2 py-2">{e.agent ?? "—"}</td>
                      <td className="px-2 py-2">{fileName(e.source_file_id)}</td>
                      <td className="px-2 py-2">{fileName(e.destination_file_id)}</td>
                      <td className="px-2 py-2">{e.duration_ms != null ? `${e.duration_ms} ms` : "—"}</td>
                      <td className="px-2 py-2">
                        {e.status === "success" ? (
                          <Badge variant="success" className="gap-1"><CheckCircle2 className="h-3 w-3" /> Success</Badge>
                        ) : (
                          <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" /> Failed</Badge>
                        )}
                      </td>
                      <td className="px-2 py-2 max-w-xs">
                        <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                          {e.detail ? JSON.stringify(e.detail) : "—"}
                        </pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
