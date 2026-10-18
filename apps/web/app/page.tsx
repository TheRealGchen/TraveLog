"use client";

import { PlusIcon } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { NewTripDialog } from "@/components/new-trip-dialog";
import { TripCard } from "@/components/trip-card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useTrips } from "@/lib/queries";

export default function TripsDashboard() {
  const trips = useTrips();
  const [creating, setCreating] = useState(false);

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 sm:py-16">
      <header className="mb-10">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Your trips</h1>
        <p className="mt-2 text-lg text-muted-foreground">Plan every day, down to the hour.</p>
      </header>

      {trips.isError && (
        <p className="mb-6 rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-destructive">
          {errorMessage(trips.error)}
        </p>
      )}

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <motion.button
          type="button"
          whileHover={{ y: -4 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          onClick={() => setCreating(true)}
          className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-primary/30 bg-primary/5 p-6 text-primary outline-none hover:border-primary/60 hover:bg-primary/10 focus-visible:ring-3 focus-visible:ring-ring/60"
        >
          <span className="flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <PlusIcon className="size-6" />
          </span>
          <span className="text-lg font-semibold">New trip</span>
        </motion.button>

        {trips.isPending &&
          Array.from({ length: 2 }, (_, i) => (
            <Skeleton key={i} className="min-h-48 rounded-2xl" />
          ))}

        {trips.data?.trips.map((trip) => <TripCard key={trip.id} trip={trip} />)}
      </div>

      {trips.data && trips.data.trips.length === 0 && (
        <p className="mt-10 text-center text-muted-foreground">
          No trips yet. Start one and add the people coming along.
        </p>
      )}

      <NewTripDialog open={creating} onOpenChange={setCreating} />
    </main>
  );
}
