// Color-coded confidence indicator: green >= 90%, yellow >= 75%, red < 75% - the exact
// thresholds given in the project spec (distinct from the backend's separate 75%
// "confident enough to auto-proceed without asking the user" threshold).
export default function ConfidencePill({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="inline-block rounded-full px-2.5 py-0.5 text-sm font-bold bg-gray-100 text-gray-400">—</span>;
  }
  const v = Number(value);
  const cls =
    v >= 90 ? "bg-green-100 text-green-700" :
    v >= 75 ? "bg-yellow-100 text-yellow-700" :
    "bg-red-100 text-red-700";
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-sm font-bold ${cls}`}>{v.toFixed(0)}%</span>;
}
