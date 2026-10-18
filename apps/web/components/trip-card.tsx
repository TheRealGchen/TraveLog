"use client";

import type { TripSummary } from "@travel/client";
import { CalendarDaysIcon, MapPinIcon } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { CountdownBadge } from "@/components/countdown-badge";
import { TravelerAvatars } from "@/components/traveler-avatars";
import { formatDateRange } from "@/lib/time";

export function TripCard({ trip }: { trip: TripSummary }) {
  return (
    <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 400, damping: 30 }}>
      <Link
        href={`/trips/${trip.id}`}
        className="group flex h-full min-h-48 flex-col justify-between rounded-2xl border bg-card p-6 shadow-sm transition-shadow outline-none hover:shadow-lg focus-visible:ring-3 focus-visible:ring-ring/60"
      >
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-xl font-semibold tracking-tight">{trip.name}</h2>
            <CountdownBadge daysUntilStart={trip.daysUntilStart} status={trip.status} />
          </div>
          {trip.destination && (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <MapPinIcon className="size-4" />
              {trip.destination}
            </p>
          )}
        </div>
        <div className="mt-6 flex items-end justify-between gap-3">
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <CalendarDaysIcon className="size-4" />
            {formatDateRange(trip.startDate, trip.endDate)}
          </p>
          <TravelerAvatars travelers={trip.travelers} />
        </div>
      </Link>
    </motion.div>
  );
}
