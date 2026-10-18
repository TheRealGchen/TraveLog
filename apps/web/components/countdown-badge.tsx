import { countdownLabel } from "@/lib/time";
import { cn } from "@/lib/utils";

export function CountdownBadge({
  daysUntilStart,
  status,
  className,
}: {
  daysUntilStart: number;
  status: string;
  className?: string;
}) {
  const label = countdownLabel(daysUntilStart, status);
  const tone =
    status === "past"
      ? "bg-muted text-muted-foreground"
      : status === "ongoing" || daysUntilStart === 0
        ? "bg-emerald-100 text-emerald-800"
        : "bg-primary/10 text-primary";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        tone,
        className,
      )}
    >
      {label}
    </span>
  );
}
