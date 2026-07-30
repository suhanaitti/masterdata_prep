"use client";

import { useState } from "react";
import FieldMappingSection from "../components/FieldMappingSection";
import UploadSlot from "../components/UploadSlot";

// Many-source / one-destination: any number of source files (add/remove freely),
// exactly one destination file slot (the backend rejects a second CONFIRMED
// destination for the same master type - see masters.py's _check_destination_conflict).
let nextSlotId = 1;

export default function UploadPage() {
  const [sourceSlotIds, setSourceSlotIds] = useState<number[]>([nextSlotId++]);

  function addSourceSlot() {
    setSourceSlotIds((ids) => [...ids, nextSlotId++]);
  }

  function removeSourceSlot(id: number) {
    setSourceSlotIds((ids) => (ids.length > 1 ? ids.filter((i) => i !== id) : ids));
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">AI ERP Master Data Mapping</h1>
        <p className="text-muted-foreground mt-1.5 max-w-2xl">
          Upload source and destination metadata, let AI generate mappings, review suggestions, and export approved mappings.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <div className="space-y-4">
          {sourceSlotIds.map((id) => (
            <UploadSlot
              key={id}
              side="source"
              showRemove={sourceSlotIds.length > 1}
              onRemove={() => removeSourceSlot(id)}
            />
          ))}
          <button
            onClick={addSourceSlot}
            type="button"
            className="text-sm border border-border rounded-md px-3 py-1.5 hover:bg-muted transition-colors"
          >
            + Add another source file
          </button>
        </div>

        <UploadSlot side="destination" showRemove={false} />
      </div>

      <FieldMappingSection />
    </div>
  );
}
