import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { MasterFile } from "../lib/types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-right">{value}</span>
    </div>
  );
}

// Real, derivable data only - no fabricated "Project"/"ERP name" values. This
// project has no `projects` table yet (Project Name / Client / Source ERP /
// Destination ERP don't exist anywhere in the schema), so those rows honestly say
// "Not set up yet" rather than inventing a fake project like "ABC SAP Migration".
export default function MappingSidebar({
  sourceFile, destFile, sourceFieldCount, destFieldCount, lastRunAt,
}: {
  sourceFile: MasterFile | null;
  destFile: MasterFile | null;
  sourceFieldCount: number;
  destFieldCount: number;
  lastRunAt: Date | null;
}) {
  const masterType = sourceFile?.confirmed_master_type || destFile?.confirmed_master_type || "—";

  return (
    <Card className="sticky top-6">
      <CardHeader>
        <CardTitle>Current Mapping</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <Row label="Project" value="Not set up yet" />
        <Row label="Source ERP" value="Not tracked yet" />
        <Row label="Destination ERP" value="Not tracked yet" />
        <Row label="Master Type" value={masterType} />
        <Row label="Source File" value={sourceFile?.filename || "—"} />
        <Row label="Destination File" value={destFile?.filename || "—"} />
        <Row label="Source Fields" value={sourceFieldCount} />
        <Row label="Destination Fields" value={destFieldCount} />
        <Row label="AI Model" value="OpenRouter / Groq (auto-fallback)" />
        <Row
          label="Last Run"
          value={lastRunAt ? lastRunAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "No runs yet"}
        />
      </CardContent>
    </Card>
  );
}
