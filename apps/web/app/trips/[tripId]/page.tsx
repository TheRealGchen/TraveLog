"use client";

import { ArrowLeftIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ActivityDialog, type ActivityDialogTarget } from "@/components/activity-dialog";
import { ItineraryTab } from "@/components/itinerary-tab";
import { ThingsToDoTab } from "@/components/things-to-do-tab";
import { TripHeader } from "@/components/trip-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, errorMessage } from "@/lib/api";
import { useTrip } from "@/lib/queries";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const trip = useTrip(tripId);
  const [dialog, setDialog] = useState<ActivityDialogTarget | null>(null);

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
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
          <Tabs defaultValue="itinerary" className="mt-10">
            <div className="flex items-center justify-between gap-3">
              <TabsList>
                <TabsTrigger value="itinerary">Itinerary</TabsTrigger>
                <TabsTrigger value="todo">Things to do</TabsTrigger>
              </TabsList>
              <Button onClick={() => setDialog({ mode: "create", date: null })}>
                <PlusIcon />
                Add activity
              </Button>
            </div>
            <TabsContent value="itinerary" className="mt-6">
              <ItineraryTab
                trip={trip.data}
                onOpen={(activity) => setDialog({ mode: "edit", activity })}
                onAdd={(date) => setDialog({ mode: "create", date })}
              />
            </TabsContent>
            <TabsContent value="todo" className="mt-6">
              <ThingsToDoTab
                trip={trip.data}
                onOpen={(activity) => setDialog({ mode: "edit", activity })}
              />
            </TabsContent>
          </Tabs>
          <ActivityDialog trip={trip.data} target={dialog} onClose={() => setDialog(null)} />
        </>
      )}
    </main>
  );
}
