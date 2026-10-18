"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { DateRangePicker, type DateRangeValue } from "@/components/date-range-picker";
import { TimezoneSelect } from "@/components/timezone-select";
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
import { useCreateTrip } from "@/lib/queries";
import { browserTimeZone } from "@/lib/time";

export function NewTripDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const createTrip = useCreateTrip();
  const [name, setName] = useState("");
  const [destination, setDestination] = useState("");
  const [timezone, setTimezone] = useState(browserTimeZone);
  const [dates, setDates] = useState<DateRangeValue>({});

  const ready = name.trim() && dates.startDate && dates.endDate;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready) return;
    createTrip.mutate(
      {
        name: name.trim(),
        destination: destination.trim() || null,
        timezone,
        startDate: dates.startDate!,
        endDate: dates.endDate!,
      },
      {
        onSuccess: (trip) => {
          onOpenChange(false);
          setName("");
          setDestination("");
          setDates({});
          router.push(`/trips/${trip.id}`);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>New trip</DialogTitle>
            <DialogDescription>Where are you going, and when?</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="trip-name">Name</Label>
            <Input
              id="trip-name"
              className="h-10"
              placeholder="Japan 2027"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="trip-destination">Destination</Label>
            <Input
              id="trip-destination"
              className="h-10"
              placeholder="Tokyo & Kyoto"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="trip-timezone">Timezone</Label>
            <TimezoneSelect id="trip-timezone" value={timezone} onChange={setTimezone} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="trip-dates">Dates</Label>
            <DateRangePicker id="trip-dates" value={dates} onChange={setDates} />
          </div>
          <DialogFooter>
            <Button type="submit" size="lg" disabled={!ready || createTrip.isPending}>
              {createTrip.isPending ? "Creating…" : "Create trip"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
