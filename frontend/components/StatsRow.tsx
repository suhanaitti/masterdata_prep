import { CheckCircle2, Clock, FileQuestion, FileX2 } from "lucide-react";
import { Card, CardContent } from "./ui/card";
import { Progress } from "./ui/progress";
import { cn } from "../lib/utils";

function StatCard({
  label, value, icon, dotClass,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  dotClass: string;
}) {
  return (
    <Card>
      <CardContent className="p-5 flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">{label}</p>
          <p className="text-3xl font-semibold tracking-tight">{value}</p>
        </div>
        <div className="relative">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">{icon}</div>
          <span className={cn("absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-white", dotClass)} />
        </div>
      </CardContent>
    </Card>
  );
}

export default function StatsRow({
  mapped, pending, unmappedSource, unmappedDestination, totalSource,
}: {
  mapped: number;
  pending: number;
  unmappedSource: number;
  unmappedDestination: number;
  totalSource: number;
}) {
  const resolved = mapped;
  const pct = totalSource > 0 ? Math.round((resolved / totalSource) * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Mapped" value={mapped} icon={<CheckCircle2 className="h-5 w-5 text-success" />} dotClass="bg-success" />
        <StatCard label="Pending Review" value={pending} icon={<Clock className="h-5 w-5 text-warning" />} dotClass="bg-warning" />
        <StatCard label="Unmapped Source" value={unmappedSource} icon={<FileQuestion className="h-5 w-5 text-muted-foreground" />} dotClass="bg-muted-foreground" />
        <StatCard label="Unmapped Destination" value={unmappedDestination} icon={<FileX2 className="h-5 w-5 text-destructive" />} dotClass="bg-destructive" />
      </div>

      {totalSource > 0 && (
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">{pct}%</span>
              <span className="text-sm text-muted-foreground">{resolved} / {totalSource} Fields Processed</span>
            </div>
            <Progress value={pct} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
