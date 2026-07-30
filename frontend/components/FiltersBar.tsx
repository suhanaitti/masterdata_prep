"use client";

import { Search } from "lucide-react";
import { Input } from "./ui/input";

export type ConfidenceFilter = "all" | "high" | "medium" | "low";
export type StatusFilter = "all" | "mapped" | "pending" | "rejected";

const selectClass =
  "h-10 rounded-md border border-input bg-white px-3 text-sm shadow-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function FiltersBar({
  search, onSearchChange,
  confidence, onConfidenceChange,
  status, onStatusChange,
}: {
  search: string;
  onSearchChange: (v: string) => void;
  confidence: ConfidenceFilter;
  onConfidenceChange: (v: ConfidenceFilter) => void;
  status: StatusFilter;
  onStatusChange: (v: StatusFilter) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 min-w-[220px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search field name..."
          className="pl-9"
        />
      </div>

      <select
        value={confidence}
        onChange={(e) => onConfidenceChange(e.target.value as ConfidenceFilter)}
        className={selectClass}
      >
        <option value="all">All confidence</option>
        <option value="high">High (&ge;80%)</option>
        <option value="medium">Medium (65-79%)</option>
        <option value="low">Low (&lt;65%)</option>
      </select>

      <select
        value={status}
        onChange={(e) => onStatusChange(e.target.value as StatusFilter)}
        className={selectClass}
      >
        <option value="all">All statuses</option>
        <option value="mapped">Mapped</option>
        <option value="pending">Pending review</option>
        <option value="rejected">Rejected</option>
      </select>
    </div>
  );
}
