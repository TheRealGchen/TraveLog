"use client";

import type { ActivityStatus, Trip } from "@travel/client";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActivityCard } from "@/components/activity-card";
import { STATUSES } from "@/components/activity-status";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useActivities, useSetActivityStatus } from "@/lib/queries";

const ALL = "all";

export function ThingsToDoTab({ trip }: { trip: Trip }) {
  const router = useRouter();
  const [status, setStatusFilter] = useState<string>(ALL);
  const [travelerId, setTravelerId] = useState<string>(ALL);
  // Filtering happens in the API (list_activities), not in the browser.
  const activities = useActivities(trip.id, {
    status: status === ALL ? undefined : (status as ActivityStatus),
    travelerId: travelerId === ALL ? undefined : travelerId,
  });
  const setStatus = useSetActivityStatus(trip.id);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3">
        <Select value={status} onValueChange={setStatusFilter}>
          <SelectTrigger aria-label="Filter by status" className="h-10 min-w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={travelerId} onValueChange={setTravelerId}>
          <SelectTrigger aria-label="Filter by traveler" className="h-10 min-w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Everyone</SelectItem>
            {trip.travelers.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {activities.isPending && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 rounded-2xl" />
          ))}
        </div>
      )}
      {activities.isError && (
        <p className="text-destructive">{errorMessage(activities.error)}</p>
      )}
      {activities.data && activities.data.activities.length === 0 && (
        <p className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">
          {status === ALL && travelerId === ALL
            ? "Nothing to do yet. Open a day to add activities."
            : "No activities match these filters."}
        </p>
      )}
      <div className="space-y-3">
        {activities.data?.activities.map((activity) => (
          <ActivityCard
            key={activity.id}
            activity={activity}
            travelers={trip.travelers}
            timeZone={trip.timezone}
            showDate
            onOpen={(a) => router.push(`/trips/${trip.id}/days/${a.date}?activity=${a.id}`)}
            onStatusChange={(s) => setStatus.mutate({ activityId: activity.id, status: s })}
          />
        ))}
      </div>
    </div>
  );
}
