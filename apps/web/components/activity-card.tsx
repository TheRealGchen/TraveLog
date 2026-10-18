"use client";

import type { Activity, ActivityStatus, Traveler } from "@travel/client";
import { ClockIcon, MapPinIcon } from "lucide-react";
import { motion } from "motion/react";

import { StatusPicker } from "@/components/activity-status";
import { TravelerAvatars } from "@/components/traveler-avatars";
import { formatShortDate, formatTimeRange } from "@/lib/time";
import { cn } from "@/lib/utils";

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
  const { schedule } = activity;
  const people = travelers.filter((t) => activity.travelerIds.includes(t.id));
  const when = [
    showDate ? (schedule.date ? formatShortDate(schedule.date) : "Unscheduled") : null,
    schedule.date ? formatTimeRange(schedule.startAt, schedule.endAt, timeZone) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <motion.div
      layout
      whileHover={{ y: -2 }}
      transition={{ type: "spring", stiffness: 500, damping: 35 }}
      role="button"
      tabIndex={0}
      aria-label={`Open ${activity.title}`}
      onClick={() => onOpen(activity)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(activity);
        }
      }}
      className={cn(
        "flex cursor-pointer items-center gap-4 rounded-2xl border bg-card p-4 shadow-sm transition-shadow outline-none hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/60",
        activity.status === "done" && "bg-card/70",
        className,
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        {when && (
          <p className="flex items-center gap-1.5 text-sm font-medium text-primary">
            <ClockIcon className="size-3.5" />
            {when}
          </p>
        )}
        <p
          className={cn(
            "truncate text-base font-semibold",
            activity.status === "done" && "text-muted-foreground line-through",
          )}
        >
          {activity.title}
        </p>
        {activity.location && (
          <p className="flex items-center gap-1.5 truncate text-sm text-muted-foreground">
            <MapPinIcon className="size-3.5 shrink-0" />
            {activity.location.name}
          </p>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <StatusPicker status={activity.status} onChange={onStatusChange} />
        <TravelerAvatars travelers={people} size="sm" />
      </div>
    </motion.div>
  );
}
