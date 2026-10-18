"use client";

import type { Activity, ActivityStatus, Traveler } from "@travel/client";
import { CalendarIcon, ClockIcon, MapPinIcon } from "lucide-react";

import { StatusPicker } from "@/components/activity-status";
import { TravelerAvatars } from "@/components/traveler-avatars";
import { formatShortDate, formatTimeRange } from "@/lib/time";
import { cn } from "@/lib/utils";

/** A roomy, fully clickable summary of one activity. */
export function ActivityCard({
  activity,
  travelers,
  timeZone,
  showDate = false,
  onOpen,
  onStatusChange,
  className,
}: {
  activity: Activity;
  travelers: Traveler[];
  timeZone: string;
  showDate?: boolean;
  onOpen: (activity: Activity) => void;
  onStatusChange: (status: ActivityStatus) => void;
  className?: string;
}) {
  const people = travelers.filter((t) => activity.travelerIds.includes(t.id));
  const done = activity.status === "done";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Open ${activity.title}`}
      onClick={() => onOpen(activity)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onOpen(activity);
        }
      }}
      className={cn(
        "flex cursor-pointer items-start gap-4 rounded-2xl border bg-card p-5 shadow-sm transition-shadow outline-none hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/60",
        done && "bg-card/70",
        className,
      )}
    >
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium text-primary">
          {showDate && (
            <span className="flex items-center gap-1.5">
              <CalendarIcon className="size-4" />
              {formatShortDate(activity.date)}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <ClockIcon className="size-4" />
            {formatTimeRange(activity.time?.startAt ?? null, activity.time?.endAt ?? null, timeZone)}
          </span>
        </p>
        <p className={cn("text-lg font-semibold", done && "text-muted-foreground line-through")}>
          {activity.title}
        </p>
        {activity.location && (
          <p className="flex items-center gap-1.5 text-muted-foreground">
            <MapPinIcon className="size-4 shrink-0" />
            {activity.location.name}
          </p>
        )}
        {activity.notes && (
          <p className="line-clamp-2 text-sm whitespace-pre-line text-muted-foreground">
            {activity.notes}
          </p>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-3">
        <StatusPicker status={activity.status} onChange={onStatusChange} />
        <TravelerAvatars travelers={people} size="sm" />
      </div>
    </div>
  );
}
