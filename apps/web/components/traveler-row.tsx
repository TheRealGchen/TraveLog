"use client";

import type { Trip, Traveler, UpdateTravelerRequest } from "@travel/client";
import { UserPlusIcon, UsersIcon } from "lucide-react";
import { useState } from "react";

import { BulkTravelersDialog } from "@/components/bulk-travelers-dialog";
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

/** Name, email, and passport inputs shared by the add and edit popovers. */
function TravelerFields({
  idPrefix,
  name,
  email,
  passport,
  onName,
  onEmail,
  onPassport,
}: {
  idPrefix: string;
  name: string;
  email: string;
  passport: string;
  onName: (v: string) => void;
  onEmail: (v: string) => void;
  onPassport: (v: string) => void;
}) {
  return (
    <>
      <div className="grid gap-1.5">
        <Label htmlFor={`${idPrefix}-name`}>Name</Label>
        <Input
          id={`${idPrefix}-name`}
          placeholder="Sam Lee"
          value={name}
          onChange={(e) => onName(e.target.value)}
          autoFocus
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${idPrefix}-email`}>Email (optional)</Label>
        <Input
          id={`${idPrefix}-email`}
          type="email"
          placeholder="sam@example.com"
          value={email}
          onChange={(e) => onEmail(e.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${idPrefix}-passport`}>Passport number (optional)</Label>
        <Input
          id={`${idPrefix}-passport`}
          placeholder="X12345678"
          value={passport}
          onChange={(e) => onPassport(e.target.value)}
        />
      </div>
    </>
  );
}

function TravelerChip({ trip, traveler }: { trip: Trip; traveler: Traveler }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(traveler.name);
  const [color, setColor] = useState(traveler.color);
  const [email, setEmail] = useState(traveler.email ?? "");
  const [passport, setPassport] = useState(traveler.passportNumber ?? "");
  const update = useUpdateTraveler(trip.id);
  const remove = useRemoveTraveler(trip.id);

  function save(event: React.FormEvent) {
    event.preventDefault();
    // Send only what changed; an emptied email or passport is cleared (null).
    const body: UpdateTravelerRequest = {};
    if (name.trim() && name.trim() !== traveler.name) body.name = name.trim();
    if (color.toLowerCase() !== traveler.color.toLowerCase()) body.color = color;
    if ((email.trim() || null) !== traveler.email) body.email = email.trim() || null;
    if ((passport.trim() || null) !== traveler.passportNumber) {
      body.passportNumber = passport.trim() || null;
    }
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
          setEmail(traveler.email ?? "");
          setPassport(traveler.passportNumber ?? "");
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
      <PopoverContent align="start" className="w-72">
        <form onSubmit={save} className="grid gap-3" aria-label={`Edit ${traveler.name}`}>
          <TravelerFields
            idPrefix={traveler.id}
            name={name}
            email={email}
            passport={passport}
            onName={setName}
            onEmail={setEmail}
            onPassport={setPassport}
          />
          <div className="flex items-center gap-2">
            <Label htmlFor={`${traveler.id}-color`}>Color</Label>
            <input
              id={`${traveler.id}-color`}
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
  const [bulkOpen, setBulkOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [passport, setPassport] = useState("");
  const add = useAddTraveler(tripId);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    add.mutate(
      {
        name: name.trim(),
        ...(email.trim() ? { email: email.trim() } : {}),
        ...(passport.trim() ? { passportNumber: passport.trim() } : {}),
      },
      {
        onSuccess: () => {
          setName("");
          setEmail("");
          setPassport("");
          setOpen(false);
        },
      },
    );
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" className="h-9 rounded-full">
            <UserPlusIcon />
            Add traveler
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72">
          <form onSubmit={submit} className="grid gap-3" aria-label="Add traveler">
            <TravelerFields
              idPrefix="new-traveler"
              name={name}
              email={email}
              passport={passport}
              onName={setName}
              onEmail={setEmail}
              onPassport={setPassport}
            />
            <Button type="submit" size="sm" disabled={!name.trim() || add.isPending}>
              Add
            </Button>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => {
                setOpen(false);
                setBulkOpen(true);
              }}
            >
              <UsersIcon />
              Add multiple…
            </Button>
          </form>
        </PopoverContent>
      </Popover>
      <BulkTravelersDialog tripId={tripId} open={bulkOpen} onOpenChange={setBulkOpen} />
    </>
  );
}
