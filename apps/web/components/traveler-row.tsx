"use client";

import type { Trip, Traveler } from "@travel/client";
import { UserPlusIcon } from "lucide-react";
import { useState } from "react";

import { TravelerAvatar } from "@/components/traveler-avatars";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAddTraveler, useRemoveTraveler, useUpdateTraveler } from "@/lib/queries";

export function TravelerRow({ trip }: { trip: Trip }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {trip.travelers.map((t) => (
        <TravelerChip key={t.id} trip={trip} traveler={t} />
      ))}
      <AddTraveler tripId={trip.id} />
    </div>
  );
}

function TravelerChip({ trip, traveler }: { trip: Trip; traveler: Traveler }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(traveler.name);
  const [color, setColor] = useState(traveler.color);
  const update = useUpdateTraveler(trip.id);
  const remove = useRemoveTraveler(trip.id);

  function save(event: React.FormEvent) {
    event.preventDefault();
    const body: { name?: string; color?: string } = {};
    if (name.trim() && name.trim() !== traveler.name) body.name = name.trim();
    if (color.toLowerCase() !== traveler.color.toLowerCase()) body.color = color;
    if (Object.keys(body).length === 0) return setOpen(false);
    update.mutate({ travelerId: traveler.id, ...body }, { onSuccess: () => setOpen(false) });
  }

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setName(traveler.name);
          setColor(traveler.color);
        }
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-full border bg-card py-1 pr-3 pl-1 text-sm font-medium shadow-xs transition-shadow outline-none hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <TravelerAvatar traveler={traveler} size="sm" className="ring-0" />
          {traveler.name}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        <form onSubmit={save} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`name-${traveler.id}`}>Name</Label>
            <Input id={`name-${traveler.id}`} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor={`color-${traveler.id}`}>Color</Label>
            <input
              id={`color-${traveler.id}`}
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 w-12 cursor-pointer rounded border bg-transparent"
            />
          </div>
          <div className="flex justify-between gap-2">
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate(traveler.id, { onSuccess: () => setOpen(false) })}
            >
              Remove
            </Button>
            <Button type="submit" size="sm" disabled={update.isPending}>
              Save
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function AddTraveler({ tripId }: { tripId: string }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const add = useAddTraveler(tripId);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate(name.trim(), {
      onSuccess: () => {
        setName("");
        setOpen(false);
      },
    });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="h-9 rounded-full">
          <UserPlusIcon />
          Add traveler
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        <form onSubmit={submit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="new-traveler-name">Name</Label>
            <Input
              id="new-traveler-name"
              placeholder="Sam"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <Button type="submit" size="sm" disabled={!name.trim() || add.isPending}>
            Add
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
