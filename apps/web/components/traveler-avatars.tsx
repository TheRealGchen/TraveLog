import type { Traveler } from "@travel/client";
import { cn } from "@/lib/utils";

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const sizes = { sm: "size-6 text-[10px]", md: "size-8 text-xs", lg: "size-10 text-sm" };

export function TravelerAvatar({
  traveler,
  size = "md",
  className,
}: {
  traveler: Traveler;
  size?: keyof typeof sizes;
  className?: string;
}) {
  return (
    <span
      title={traveler.name}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ring-2 ring-card select-none",
        sizes[size],
        className,
      )}
      style={{ backgroundColor: traveler.color }}
    >
      {initials(traveler.name)}
    </span>
  );
}

/** Overlapping avatars, with a "+N" bubble past `max`. */
export function TravelerAvatars({
  travelers,
  max = 4,
  size = "md",
}: {
  travelers: Traveler[];
  max?: number;
  size?: keyof typeof sizes;
}) {
  if (travelers.length === 0) return null;
  const shown = travelers.slice(0, max);
  const rest = travelers.length - shown.length;
  return (
    <div className="flex -space-x-2" aria-label={travelers.map((t) => t.name).join(", ")}>
      {shown.map((t) => (
        <TravelerAvatar key={t.id} traveler={t} size={size} />
      ))}
      {rest > 0 && (
        <span
          className={cn(
            "inline-flex items-center justify-center rounded-full bg-muted font-semibold text-muted-foreground ring-2 ring-card",
            sizes[size],
          )}
        >
          +{rest}
        </span>
      )}
    </div>
  );
}
