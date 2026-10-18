"use client";

import type { ActivityStatus } from "@travel/client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export const STATUSES: { value: ActivityStatus; label: string; className: string }[] = [
  { value: "idea", label: "Idea", className: "bg-amber-100 text-amber-800" },
  { value: "planned", label: "Planned", className: "bg-primary/10 text-primary" },
  { value: "done", label: "Done", className: "bg-emerald-100 text-emerald-800" },
];

export function StatusBadge({ status }: { status: ActivityStatus }) {
  const s = STATUSES.find((x) => x.value === status) ?? STATUSES[0];
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", s.className)}>
      {s.label}
    </span>
  );
}

/** A compact status picker that sits on a card without opening it. */
export function StatusPicker({
  status,
  onChange,
}: {
  status: ActivityStatus;
  onChange: (status: ActivityStatus) => void;
}) {
  return (
    <div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <Select value={status} onValueChange={(v) => onChange(v as ActivityStatus)}>
        <SelectTrigger
          size="sm"
          aria-label="Status"
          className="h-7 gap-1 rounded-full border-0 bg-transparent px-1 shadow-none hover:bg-muted"
        >
          <SelectValue>
            <StatusBadge status={status} />
          </SelectValue>
        </SelectTrigger>
        <SelectContent align="end">
          {STATUSES.map((s) => (
            <SelectItem key={s.value} value={s.value}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
