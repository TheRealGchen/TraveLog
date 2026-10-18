"use client";

import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { Activity, Trip } from "@travel/client";
import { PlusIcon, SparklesIcon } from "lucide-react";
import { useState } from "react";

import { ActivityCard } from "@/components/activity-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useItinerary, useMoveActivity, useSetActivityStatus } from "@/lib/queries";
import { formatDayHeader } from "@/lib/time";
import { cn } from "@/lib/utils";

const UNSCHEDULED = "unscheduled";

/** A day section (or the Unscheduled section) that activities can be dropped on. */
function DropZone({
  id,
  className,
  children,
  ...props
}: { id: string } & React.ComponentProps<"section">) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <section
      ref={setNodeRef}
      className={cn(
        "rounded-3xl transition-colors",
        isOver && "bg-primary/5 ring-2 ring-primary/40",
        className,
      )}
      {...props}
    >
      {children}
    </section>
  );
}

function Draggable({ activity, children }: { activity: Activity; children: React.ReactNode }) {
  const { setNodeRef, listeners, isDragging } = useDraggable({ id: activity.id, data: activity });
  return (
    <div ref={setNodeRef} {...listeners} className={cn("touch-manipulation", isDragging && "opacity-40")}>
      {children}
    </div>
  );
}

export function ItineraryTab({
  trip,
  onOpen,
  onAdd,
}: {
  trip: Trip;
  onOpen: (activity: Activity) => void;
  onAdd: (date: string | null) => void;
}) {
  const itinerary = useItinerary(trip.id);
  const setStatus = useSetActivityStatus(trip.id);
  const move = useMoveActivity(trip.id);
  const [dragging, setDragging] = useState<Activity | null>(null);
  // A small movement threshold keeps clicks (open the dialog) separate from drags.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  if (itinerary.isPending) {
    return (
      <div className="space-y-6">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-3">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-20 rounded-2xl" />
          </div>
        ))}
      </div>
    );
  }
  if (itinerary.isError) {
    return <p className="text-destructive">{errorMessage(itinerary.error)}</p>;
  }

  const card = (activity: Activity) => (
    <Draggable key={activity.id} activity={activity}>
      <ActivityCard
        activity={activity}
        travelers={trip.travelers}
        timeZone={trip.timezone}
        onOpen={onOpen}
        onStatusChange={(status) => setStatus.mutate({ activityId: activity.id, status })}
      />
    </Draggable>
  );

  function onDragStart(event: DragStartEvent) {
    setDragging(event.active.data.current as Activity);
  }

  function onDragEnd(event: DragEndEvent) {
    setDragging(null);
    const activity = event.active.data.current as Activity;
    if (!event.over) return;
    const date = event.over.id === UNSCHEDULED ? null : String(event.over.id);
    if (date === activity.schedule.date) return;
    move.mutate({ activityId: activity.id, body: { date } });
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setDragging(null)}
    >
      <div className="space-y-8">
        {itinerary.data.days.map((day) => (
          <DropZone
            key={day.date}
            id={day.date}
            aria-label={formatDayHeader(day.dayNumber, day.date)}
            className="-mx-2 p-2"
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold tracking-tight">
                {formatDayHeader(day.dayNumber, day.date)}
              </h3>
              {day.activities.length > 0 && (
                <Button variant="ghost" size="sm" onClick={() => onAdd(day.date)}>
                  <PlusIcon />
                  Add
                </Button>
              )}
            </div>
            <div className="space-y-3">
              {day.activities.length > 0 ? (
                day.activities.map(card)
              ) : (
                <div className="flex items-center justify-between rounded-2xl border border-dashed px-4 py-3 text-muted-foreground">
                  <span>Nothing planned</span>
                  <Button variant="ghost" size="sm" onClick={() => onAdd(day.date)}>
                    <PlusIcon />
                    Add
                  </Button>
                </div>
              )}
            </div>
          </DropZone>
        ))}

        <DropZone id={UNSCHEDULED} aria-label="Unscheduled" className="bg-muted/60 p-4 sm:p-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
              <SparklesIcon className="size-4 text-amber-500" />
              Unscheduled
            </h3>
            <Button variant="ghost" size="sm" onClick={() => onAdd(null)}>
              <PlusIcon />
              Add idea
            </Button>
          </div>
          <div className="space-y-3">
            {itinerary.data.unscheduled.length > 0 ? (
              itinerary.data.unscheduled.map(card)
            ) : (
              <p className="px-1 text-sm text-muted-foreground">
                Ideas without a day land here.
              </p>
            )}
          </div>
        </DropZone>
      </div>
      <DragOverlay>
        {dragging && (
          <ActivityCard
            activity={dragging}
            travelers={trip.travelers}
            timeZone={trip.timezone}
            onOpen={() => {}}
            onStatusChange={() => {}}
            className="rotate-1 shadow-xl"
          />
        )}
      </DragOverlay>
    </DndContext>
  );
}
