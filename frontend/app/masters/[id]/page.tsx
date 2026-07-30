"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ConfidencePill from "../../../components/ConfidencePill";
import { getMasterFile } from "../../../lib/api";
import { MasterFileDetail } from "../../../lib/types";

export default function MasterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<MasterFileDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMasterFile(id).then(setDetail).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="rounded-md bg-red-50 text-red-700 text-sm px-3 py-2">{error}</div>;
  if (!detail) return <p>Loading...</p>;

  const { master_file, fields } = detail;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">{master_file.filename}</h1>
      <p className="text-gray-600 mb-4">
        <span className="capitalize">{master_file.side}</span> &middot; Master type:{" "}
        <strong>{master_file.confirmed_master_type || master_file.detected_master_type || "—"}</strong>{" "}
        <ConfidencePill value={master_file.detection_confidence} /> &middot; Status: {master_file.status}
      </p>

      {master_file.business_purpose && (
        <p className="text-sm text-gray-700 italic mb-3">{master_file.business_purpose}</p>
      )}

      {master_file.consolidation_conflicts.length > 0 && (
        <div className="mb-4 rounded-md bg-yellow-50 px-3 py-2 text-sm">
          <p className="font-medium text-yellow-800 mb-1">
            Conflicts resolved across chunks ({master_file.consolidation_conflicts.length}):
          </p>
          <ul className="list-disc list-inside text-yellow-800">
            {master_file.consolidation_conflicts.map((c) => (
              <li key={c.column_name}>
                <span className="font-medium">{c.column_name}</span>: {c.issue} — {c.resolution}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border-b border-gray-200">Column</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Description</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Type</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Length</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Mandatory</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Key</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Confidence</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Remarks</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.column_name}>
                <td className="px-3 py-2 border-b border-gray-100">{f.column_name}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.ai_description}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.data_type}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.estimated_length ?? "—"}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.is_mandatory ? "Yes" : "No"}</td>
                <td className="px-3 py-2 border-b border-gray-100">
                  {[f.is_primary_key && "PK", f.is_business_identifier && "Business ID"].filter(Boolean).join(", ") || "—"}
                </td>
                <td className="px-3 py-2 border-b border-gray-100"><ConfidencePill value={f.confidence_score} /></td>
                <td className="px-3 py-2 border-b border-gray-100">{f.ai_remarks || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {fields.length === 0 && (
        <p className="text-gray-500 mt-4">No field metadata yet - this file may still be pending confirmation.</p>
      )}
    </div>
  );
}
