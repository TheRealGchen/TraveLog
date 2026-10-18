"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { DaysTab } from "@/components/days-tab";
import { ThingsToDoTab } from "@/components/things-to-do-tab";
import { TripHeader } from "@/components/trip-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, errorMessage } from "@/lib/api";
import { useTrip } from "@/lib/queries";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const trip = useTrip(tripId);

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-1.5 rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ArrowLeftIcon className="size-4" />
        All trips
      </Link>

      {trip.isPending && (
        <div className="space-y-4">
          <Skeleton className="h-12 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-9 w-64 rounded-full" />
        </div>
      )}

      {trip.isError && (
        <div className="rounded-2xl border p-8 text-center">
          <p className="text-lg font-semibold">
            {trip.error instanceof ApiError && trip.error.status === 404
              ? "This trip doesn't exist (anymore)."
              : "Couldn't load this trip."}
          </p>
          <p className="mt-2 text-muted-foreground">{errorMessage(trip.error)}</p>
        </div>
      )}

      {trip.data && (
        <>
          <TripHeader trip={trip.data} />
          <Tabs defaultValue="days" className="mt-10">
            <TabsList>
              <TabsTrigger value="days">Days</TabsTrigger>
              <TabsTrigger value="todo">Things to do</TabsTrigger>
            </TabsList>
            <TabsContent value="days" className="mt-6">
              <DaysTab trip={trip.data} />
            </TabsContent>
            <TabsContent value="todo" className="mt-6">
              <ThingsToDoTab trip={trip.data} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </main>
  );
}
