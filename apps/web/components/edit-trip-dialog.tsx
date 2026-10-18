"use client";

import type { Trip, UpdateTripRequest } from "@travel/client";
import { Trash2Icon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DateRangePicker, type DateRangeValue } from "@/components/date-range-picker";
import { TimezoneSelect } from "@/components/timezone-select";
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
import { useDeleteTrip, useUpdateTrip } from "@/lib/queries";

export function EditTripDialog({
  trip,
  open,
  onOpenChange,
}: {
  trip: Trip;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {open && <EditTripForm trip={trip} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function EditTripForm({ trip, onDone }: { trip: Trip; onDone: () => void }) {
  const router = useRouter();
  const update = useUpdateTrip(trip.id);
  const remove = useDeleteTrip(trip.id);
  const [name, setName] = useState(trip.name);
  const [destination, setDestination] = useState(trip.destination ?? "");
  const [timezone, setTimezone] = useState(trip.timezone);
  const [dates, setDates] = useState<DateRangeValue>({
    startDate: trip.startDate,
    endDate: trip.endDate,
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const body: UpdateTripRequest = {};
    if (name.trim() !== trip.name) body.name = name.trim();
    if ((destination.trim() || null) !== trip.destination) body.destination = destination.trim() || null;
    if (timezone !== trip.timezone) body.timezone = timezone;
    if (dates.startDate && dates.startDate !== trip.startDate) body.startDate = dates.startDate;
    if (dates.endDate && dates.endDate !== trip.endDate) body.endDate = dates.endDate;
    if (Object.keys(body).length === 0) return onDone();
    update.mutate(body, { onSuccess: onDone });
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>Edit trip</DialogTitle>
        <DialogDescription>
          Changing the timezone keeps every activity at the same moment in time.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="edit-trip-name">Name</Label>
        <Input id="edit-trip-name" className="h-10" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="edit-trip-destination">Destination</Label>
        <Input
          id="edit-trip-destination"
          className="h-10"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="edit-trip-timezone">Timezone</Label>
        <TimezoneSelect id="edit-trip-timezone" value={timezone} onChange={setTimezone} />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="edit-trip-dates">Dates</Label>
        <DateRangePicker id="edit-trip-dates" value={dates} onChange={setDates} />
      </div>
      <DialogFooter className="items-center gap-2 sm:justify-between">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button type="button" variant="destructive">
              <Trash2Icon />
              Delete trip
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete “{trip.name}”?</AlertDialogTitle>
              <AlertDialogDescription>
                The trip and all of its activities will be deleted. This can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                variant="destructive"
                onClick={() => remove.mutate(undefined, { onSuccess: () => router.push("/") })}
              >
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <Button type="submit" size="lg" disabled={!name.trim() || update.isPending}>
          {update.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
