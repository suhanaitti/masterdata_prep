import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { cn } from "../lib/utils";

export type StepStatus = "done" | "active" | "pending";

export interface TimelineStep {
  label: string;
  status: StepStatus;
}

// Steps mirror the ACTUAL backend pipeline (excel_reader -> master_classifier ->
// metadata_generator [chunked] -> field_mapping_engine -> human accept/reject), not
// a generic placeholder list - see masters.py/field_mapping_engine.py for each stage.
export default function ProcessingTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Processing Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-4">
          {steps.map((step, i) => (
            <div key={step.label} className="flex items-center gap-2">
              <div className="flex items-center gap-2 rounded-full border border-border px-3 py-1.5 bg-white">
                {step.status === "done" && <CheckCircle2 className="h-4 w-4 text-success" />}
                {step.status === "active" && <Loader2 className="h-4 w-4 text-primary animate-spin" />}
                {step.status === "pending" && <Circle className="h-4 w-4 text-muted-foreground" />}
                <span
                  className={cn(
                    "text-sm font-medium",
                    step.status === "pending" ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {step.label}
                </span>
              </div>
              {i < steps.length - 1 && <span className="text-muted-foreground">&rarr;</span>}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
