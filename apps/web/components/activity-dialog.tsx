"use client";

import type {
  Activity,
  ActivityStatus,
  Trip,
  UpdateActivityRequest,
} from "@travel/client";
import { CalendarIcon, Trash2Icon, XIcon } from "lucide-react";
import { useState } from "react";

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
import { Calendar } from "@/components/ui/calendar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAddActivity, useDeleteActivity, useUpdateActivity } from "@/lib/queries";
import {
  formatDateOnly,
  formatShortDate,
  localRangeToUtc,
  parseDateOnly,
  utcToLocalTime,
} from "@/lib/time";
import { cn } from "@/lib/utils";

export type ActivityDialogTarget =
  | { mode: "create"; date: string | null }
  | { mode: "edit"; activity: Activity };

interface FormState {
  title: string;
  date: string | null;
  start: string;
  end: string;
  location: string;
  notes: string;
  status: ActivityStatus | undefined;
  travelerIds: string[];
}

function initialState(target: ActivityDialogTarget, timeZone: string): FormState {
  if (target.mode === "create") {
    return {
      title: "",
      date: target.date,
      start: "",
      end: "",
      location: "",
      notes: "",
      status: undefined,
      travelerIds: [],
    };
  }
  const a = target.activity;
  return {
    title: a.title,
    date: a.schedule.date,
    start: a.schedule.startAt ? utcToLocalTime(a.schedule.startAt, timeZone) : "",
    end: a.schedule.endAt ? utcToLocalTime(a.schedule.endAt, timeZone) : "",
    location: a.location?.name ?? "",
    notes: a.notes ?? "",
    status: a.status,
    travelerIds: a.travelerIds,
  };
}

function scheduleFrom(form: FormState, timeZone: string) {
  if (!form.date) return null;
  if (!form.start) return { date: form.date, startAt: null, endAt: null };
  return { date: form.date, ...localRangeToUtc(form.date, form.start, form.end || null, timeZone) };
}

export function ActivityDialog({
  trip,
  target,
  onClose,
}: {
  trip: Trip;
  target: ActivityDialogTarget | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        {target && (
          <ActivityForm
            key={target.mode === "edit" ? target.activity.id : `new-${target.date}`}
            trip={trip}
            target={target}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ActivityForm({
  trip,
  target,
  onClose,
}: {
  trip: Trip;
  target: ActivityDialogTarget;
  onClose: () => void;
}) {
  const tz = trip.timezone;
  const [form, setForm] = useState(() => initialState(target, tz));
  const [dateOpen, setDateOpen] = useState(false);
  const addActivity = useAddActivity(trip.id);
  const updateActivity = useUpdateActivity(trip.id);
  const deleteActivity = useDeleteActivity(trip.id);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const pending = addActivity.isPending || updateActivity.isPending;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const schedule = scheduleFrom(form, tz);
    const location = form.location.trim() ? { name: form.location.trim() } : null;
    const notes = form.notes.trim() || null;
    if (target.mode === "create") {
      addActivity.mutate(
        {
          title: form.title.trim(),
          schedule,
          location,
          notes,
          status: form.status ?? null,
          travelerIds: form.travelerIds,
        },
        { onSuccess: onClose },
      );
      return;
    }
    // Send only what changed, so concurrent edits to other fields (say, by an agent) survive.
    const a = target.activity;
    const body: UpdateActivityRequest = {};
    if (form.title.trim() !== a.title) body.title = form.title.trim();
    const before = a.schedule;
    if (
      (schedule?.date ?? null) !== before.date ||
      (schedule?.startAt ?? null) !== before.startAt ||
      (schedule?.endAt ?? null) !== before.endAt
    ) {
      body.schedule = schedule;
    }
    if ((location?.name ?? null) !== (a.location?.name ?? null)) body.location = location;
    if (notes !== a.notes) body.notes = notes;
    if (form.status && form.status !== a.status) body.status = form.status;
    if (form.travelerIds.join() !== a.travelerIds.join()) body.travelerIds = form.travelerIds;
    if (Object.keys(body).length === 0) return onClose();
    updateActivity.mutate({ activityId: a.id, body }, { onSuccess: onClose });
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>{target.mode === "create" ? "New activity" : "Edit activity"}</DialogTitle>
        <DialogDescription>Times are in {tz.replaceAll("_", " ")}.</DialogDescription>
      </DialogHeader>

      <div className="grid gap-2">
        <Label htmlFor="activity-title">Title</Label>
        <Input
          id="activity-title"
          className="h-10"
          placeholder="teamLab Planets"
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          autoFocus={target.mode === "create"}
          required
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="activity-date">Date</Label>
        <div className="flex gap-2">
          <Popover open={dateOpen} onOpenChange={setDateOpen}>
            <PopoverTrigger asChild>
              <Button
                id="activity-date"
                type="button"
                variant="outline"
                className={cn(
                  "h-10 flex-1 justify-start gap-2 font-normal",
                  !form.date && "text-muted-foreground",
                )}
              >
                <CalendarIcon />
                {form.date ? formatShortDate(form.date) : "Unscheduled"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={form.date ? parseDateOnly(form.date) : undefined}
                defaultMonth={parseDateOnly(form.date ?? trip.startDate)}
                disabled={[
                  { before: parseDateOnly(trip.startDate) },
                  { after: parseDateOnly(trip.endDate) },
                ]}
                onSelect={(day) => {
                  set("date", day ? formatDateOnly(day) : null);
                  setDateOpen(false);
                }}
              />
            </PopoverContent>
          </Popover>
          {form.date && (
            <Button
              type="button"
              variant="ghost"
              size="icon-lg"
              aria-label="Clear date"
              className="size-10"
              onClick={() => setForm((f) => ({ ...f, date: null, start: "", end: "" }))}
            >
              <XIcon />
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2">
          <Label htmlFor="activity-start">Start time</Label>
          <Input
            id="activity-start"
            type="time"
            className="h-10"
            value={form.start}
            disabled={!form.date}
            onChange={(e) =>
              setForm((f) => ({ ...f, start: e.target.value, end: e.target.value ? f.end : "" }))
            }
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="activity-end">End time</Label>
          <Input
            id="activity-end"
            type="time"
            className="h-10"
            value={form.end}
            disabled={!form.date || !form.start}
            onChange={(e) => set("end", e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="activity-location">Location</Label>
        <Input
          id="activity-location"
          className="h-10"
          placeholder="Toyosu"
          value={form.location}
          onChange={(e) => set("location", e.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="activity-notes">Notes</Label>
        <Textarea
          id="activity-notes"
          placeholder="Book tickets ahead"
          value={form.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="activity-status">Status</Label>
        <Select
          value={form.status ?? ""}
          onValueChange={(v) => set("status", v as ActivityStatus)}
        >
          <SelectTrigger id="activity-status" className="h-10 w-full">
            <SelectValue placeholder="Automatic (idea, or planned once it has a date)" />
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

      {trip.travelers.length > 0 && (
        <fieldset className="grid gap-2">
          <legend className="mb-2 text-sm font-medium">Who&apos;s going</legend>
          <div className="flex flex-wrap gap-2">
            {trip.travelers.map((t) => {
              const on = form.travelerIds.includes(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    set(
                      "travelerIds",
                      on ? form.travelerIds.filter((id) => id !== t.id) : [...form.travelerIds, t.id],
                    )
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

      <DialogFooter className="items-center gap-2 sm:justify-between">
        {target.mode === "edit" ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="destructive">
                <Trash2Icon />
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete “{target.activity.title}”?</AlertDialogTitle>
                <AlertDialogDescription>This can&apos;t be undone.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  onClick={() =>
                    deleteActivity.mutate(target.activity.id, { onSuccess: onClose })
                  }
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <span />
        )}
        <Button type="submit" size="lg" disabled={!form.title.trim() || pending}>
          {pending ? "Saving…" : target.mode === "create" ? "Add activity" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
