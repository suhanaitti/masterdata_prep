"use client";

import { useEffect, useState } from "react";
import ConfidencePill from "../../components/ConfidencePill";
import { deleteMasterFile, listMasterFiles } from "../../lib/api";
import { MasterFile } from "../../lib/types";

export default function MastersListPage() {
  const [files, setFiles] = useState<MasterFile[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listMasterFiles().then(setFiles).catch((e) => setError(e.message));
  }

  useEffect(refresh, []);

  async function onDelete(id: number) {
    if (!confirm("Delete this file and all its generated metadata?")) return;
    try {
      await deleteMasterFile(id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Uploaded master files</h1>
      {error && <div className="rounded-md bg-red-50 text-red-700 text-sm px-3 py-2 mb-4">{error}</div>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left px-3 py-2 border-b border-gray-200">Filename</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Side</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Master type</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Confidence</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Status</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Rows</th>
              <th className="text-left px-3 py-2 border-b border-gray-200">Uploaded</th>
              <th className="text-left px-3 py-2 border-b border-gray-200"></th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.id}>
                <td className="px-3 py-2 border-b border-gray-100">
                  <a href={`/masters/${f.id}`} className="text-blue-600 hover:underline">{f.filename}</a>
                </td>
                <td className="px-3 py-2 border-b border-gray-100 capitalize">{f.side}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.confirmed_master_type || f.detected_master_type || "—"}</td>
                <td className="px-3 py-2 border-b border-gray-100"><ConfidencePill value={f.detection_confidence} /></td>
                <td className="px-3 py-2 border-b border-gray-100">{f.status}</td>
                <td className="px-3 py-2 border-b border-gray-100">{f.row_count ?? "—"}</td>
                <td className="px-3 py-2 border-b border-gray-100">{new Date(f.uploaded_at).toLocaleString()}</td>
                <td className="px-3 py-2 border-b border-gray-100">
                  <button onClick={() => onDelete(f.id)} className="text-xs text-red-600 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {files.length === 0 && !error && <p className="text-gray-500 mt-4">No files uploaded yet.</p>}
    </div>
  );
}
