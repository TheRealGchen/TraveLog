"use client";

import type { Activity, Day, Trip, UpdateActivityRequest } from "@travel/client";
import { Trash2Icon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";

import { ActivityCard } from "@/components/activity-card";
import { STATUSES } from "@/components/activity-status";
import { TravelerAvatar } from "@/components/traveler-avatars";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteActivity,
  useMoveActivity,
  useSetActivityStatus,
  useUpdateActivity,
} from "@/lib/queries";
import { addDaysToDateOnly, formatDayHeader, localRangeToUtc, utcToLocalTime } from "@/lib/time";
import { cn } from "@/lib/utils";

/** An activity on the day page: a card that expands in place into its editor. */
export function ActivityItem({
  activity,
  day,
  trip,
  expanded,
  onToggle,
}: {
  activity: Activity;
  day: Day;
  trip: Trip;
  expanded: boolean;
  onToggle: (open: boolean) => void;
}) {
  const setStatus = useSetActivityStatus(trip.id);
  return (
    <motion.div layout transition={{ type: "spring", stiffness: 500, damping: 40 }}>
      <AnimatePresence mode="wait" initial={false}>
        {expanded ? (
          <motion.div
            key="editor"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <ActivityEditor
              activity={activity}
              day={day}
              trip={trip}
              onClose={() => onToggle(false)}
            />
          </motion.div>
        ) : (
          <motion.div
            key="card"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
          >
            <ActivityCard
              activity={activity}
              travelers={trip.travelers}
              timeZone={trip.timezone}
              onOpen={() => onToggle(true)}
              onStatusChange={(status) => setStatus.mutate({ activityId: activity.id, status })}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function ActivityEditor({
  activity,
  day,
  trip,
  onClose,
}: {
  activity: Activity;
  day: Day;
  trip: Trip;
  onClose: () => void;
}) {
  const tz = trip.timezone;
  const [title, setTitle] = useState(activity.title);
  const [start, setStart] = useState(activity.time ? utcToLocalTime(activity.time.startAt, tz) : "");
  const [end, setEnd] = useState(
    activity.time?.endAt ? utcToLocalTime(activity.time.endAt, tz) : "",
  );
  const [location, setLocation] = useState(activity.location?.name ?? "");
  const [notes, setNotes] = useState(activity.notes ?? "");
  const [status, setStatus] = useState(activity.status);
  const [travelerIds, setTravelerIds] = useState(activity.travelerIds);
  const update = useUpdateActivity(trip.id);
  const move = useMoveActivity(trip.id);
  const remove = useDeleteActivity(trip.id);

  const tripDays: { date: string; dayNumber: number }[] = [];
  for (let d = trip.startDate, n = 1; d <= trip.endDate; d = addDaysToDateOnly(d, 1), n++) {
    tripDays.push({ date: d, dayNumber: n });
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    // Send only what changed, so concurrent edits to other fields (say, by an agent) survive.
    const body: UpdateActivityRequest = {};
    if (title.trim() && title.trim() !== activity.title) body.title = title.trim();
    const time = start ? localRangeToUtc(day.date, start, end || null, tz) : null;
    if (
      (time?.startAt ?? null) !== (activity.time?.startAt ?? null) ||
      (time?.endAt ?? null) !== (activity.time?.endAt ?? null)
    ) {
      body.time = time;
    }
    const loc = location.trim() ? { name: location.trim() } : null;
    if ((loc?.name ?? null) !== (activity.location?.name ?? null)) body.location = loc;
    const n = notes.trim() || null;
    if (n !== activity.notes) body.notes = n;
    if (status !== activity.status) body.status = status;
    if (travelerIds.join() !== activity.travelerIds.join()) body.travelerIds = travelerIds;
    if (Object.keys(body).length === 0) return onClose();
    update.mutate({ activityId: activity.id, body }, { onSuccess: onClose });
  }

  function moveTo(date: string) {
    move.mutate(
      { activityId: activity.id, body: { date } },
      {
        onSuccess: (moved) => {
          const target = tripDays.find((d) => d.date === moved.date);
          toast.success(
            `Moved “${moved.title}” to ${target ? formatDayHeader(target.dayNumber, moved.date) : moved.date}`,
          );
          onClose();
        },
      },
    );
  }

  return (
    <form
      onSubmit={save}
      className="grid gap-5 rounded-2xl border-2 border-primary/30 bg-card p-5 shadow-lg sm:p-6"
      aria-label={`Edit ${activity.title}`}
    >
      <Input
        aria-label="Title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-12 text-xl font-semibold"
        autoFocus
        required
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-2">
            <Label htmlFor={`start-${activity.id}`}>Start</Label>
            <Input
              id={`start-${activity.id}`}
              type="time"
              className="h-10"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                if (!e.target.value) setEnd("");
              }}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`end-${activity.id}`}>End</Label>
            <Input
              id={`end-${activity.id}`}
              type="time"
              className="h-10"
              value={end}
              disabled={!start}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`location-${activity.id}`}>Location</Label>
          <Input
            id={`location-${activity.id}`}
            className="h-10"
            placeholder="Toyosu"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor={`notes-${activity.id}`}>Notes</Label>
        <Textarea
          id={`notes-${activity.id}`}
          placeholder="Book tickets ahead"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor={`status-${activity.id}`}>Status</Label>
          <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
            <SelectTrigger id={`status-${activity.id}`} className="h-10 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`move-${activity.id}`}>Day</Label>
          <Select value={day.date} onValueChange={moveTo} disabled={move.isPending}>
            <SelectTrigger id={`move-${activity.id}`} className="h-10 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {tripDays.map((d) => (
                <SelectItem key={d.date} value={d.date}>
                  {formatDayHeader(d.dayNumber, d.date)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {trip.travelers.length > 0 && (
        <fieldset className="grid gap-2">
          <legend className="mb-2 text-sm font-medium">Who&apos;s going</legend>
          <div className="flex flex-wrap gap-2">
            {trip.travelers.map((t) => {
              const on = travelerIds.includes(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setTravelerIds(on ? travelerIds.filter((id) => id !== t.id) : [...travelerIds, t.id])
                  }
                  className={cn(
                    "flex items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    on ? "border-primary bg-primary/10" : "opacity-60 hover:opacity-100",
                  )}
                >
                  <TravelerAvatar traveler={t} size="sm" className="ring-0" />
                  {t.name}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="destructive">
              <Trash2Icon />
              Delete
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete “{activity.title}”?</AlertDialogTitle>
              <AlertDialogDescription>This can&apos;t be undone.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                onClick={() => remove.mutate(activity.id, { onSuccess: onClose })}
              >
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="lg" disabled={!title.trim() || update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </form>
  );
}
