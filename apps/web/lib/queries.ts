"use client";

import type {
  Activity,
  ActivityStatus,
  AddActivityRequest,
  CreateTripRequest,
  Itinerary,
  MoveActivityRequest,
  Trip,
  UpdateActivityRequest,
  UpdateTripRequest,
} from "@travel/client";
import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { api, errorMessage, unwrap } from "./api";

/** Poll the open trip so edits made by agents through the API show up. */
const POLL_MS = 10_000;

export interface ActivityFilters {
  status?: ActivityStatus;
  travelerId?: string;
}

export const keys = {
  trips: ["trips"] as const,
  trip: (tripId: string) => ["trip", tripId] as const,
  itinerary: (tripId: string) => ["itinerary", tripId] as const,
  activities: (tripId: string, filters?: ActivityFilters) =>
    filters ? (["activities", tripId, filters] as const) : (["activities", tripId] as const),
};

function onError(error: unknown) {
  toast.error(errorMessage(error));
}

// Queries

export function useTrips() {
  return useQuery({
    queryKey: keys.trips,
    queryFn: () => unwrap(api.GET("/v1/trips", { params: { query: { sort: "startDate" } } })),
  });
}

export function useTrip(tripId: string) {
  return useQuery({
    queryKey: keys.trip(tripId),
    queryFn: () => unwrap(api.GET("/v1/trips/{tripId}", { params: { path: { tripId } } })),
    refetchInterval: POLL_MS,
  });
}

export function useItinerary(tripId: string) {
  return useQuery({
    queryKey: keys.itinerary(tripId),
    queryFn: () =>
      unwrap(api.GET("/v1/trips/{tripId}/itinerary", { params: { path: { tripId } } })),
    refetchInterval: POLL_MS,
  });
}

export function useActivities(tripId: string, filters: ActivityFilters) {
  return useQuery({
    queryKey: keys.activities(tripId, filters),
    queryFn: () =>
      unwrap(
        api.GET("/v1/trips/{tripId}/activities", {
          params: { path: { tripId }, query: filters },
        }),
      ),
    refetchInterval: POLL_MS,
  });
}

// Cache helpers

function refreshTrip(qc: QueryClient, tripId: string, trip?: Trip) {
  if (trip) qc.setQueryData(keys.trip(tripId), trip);
  void qc.invalidateQueries({ queryKey: keys.trips });
  void qc.invalidateQueries({ queryKey: keys.itinerary(tripId) });
}

function refreshActivities(qc: QueryClient, tripId: string) {
  void qc.invalidateQueries({ queryKey: keys.itinerary(tripId) });
  void qc.invalidateQueries({ queryKey: keys.activities(tripId) });
}

type Snapshot = [readonly unknown[], unknown][];

/** Apply an optimistic change to every cached view of the trip's activities. */
async function optimistic(
  qc: QueryClient,
  tripId: string,
  updateItinerary: (it: Itinerary) => Itinerary,
  updateActivity: (a: Activity) => Activity | null,
): Promise<Snapshot> {
  await qc.cancelQueries({ queryKey: keys.itinerary(tripId) });
  await qc.cancelQueries({ queryKey: keys.activities(tripId) });
  const snapshot: Snapshot = [
    ...qc.getQueriesData({ queryKey: keys.itinerary(tripId) }),
    ...qc.getQueriesData({ queryKey: keys.activities(tripId) }),
  ];
  qc.setQueryData<Itinerary>(keys.itinerary(tripId), (it) => it && updateItinerary(it));
  qc.setQueriesData<{ activities: Activity[] }>({ queryKey: keys.activities(tripId) }, (list) =>
    list
      ? {
          activities: list.activities
            .map(updateActivity)
            .filter((a): a is Activity => a !== null),
        }
      : list,
  );
  return snapshot;
}

function rollback(qc: QueryClient, snapshot: Snapshot | undefined) {
  for (const [key, data] of snapshot ?? []) qc.setQueryData(key, data);
}

function mapItinerary(it: Itinerary, fn: (a: Activity) => Activity): Itinerary {
  return {
    ...it,
    days: it.days.map((d) => ({ ...d, activities: d.activities.map(fn) })),
    unscheduled: it.unscheduled.map(fn),
  };
}

// Trip mutations

export function useCreateTrip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTripRequest) => unwrap(api.POST("/v1/trips", { body })),
    onSuccess: (trip) => {
      qc.setQueryData(keys.trip(trip.id), trip);
      void qc.invalidateQueries({ queryKey: keys.trips });
    },
    onError,
  });
}

export function useUpdateTrip(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateTripRequest) =>
      unwrap(api.PATCH("/v1/trips/{tripId}", { params: { path: { tripId } }, body })),
    onSuccess: (trip) => {
      refreshTrip(qc, tripId, trip);
      refreshActivities(qc, tripId);
    },
    onError,
  });
}

export function useDeleteTrip(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/v1/trips/{tripId}", { params: { path: { tripId } } })),
    onSuccess: () => {
      qc.removeQueries({ queryKey: keys.trip(tripId) });
      void qc.invalidateQueries({ queryKey: keys.trips });
    },
    onError,
  });
}

// Traveler mutations

export function useAddTraveler(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.POST("/v1/trips/{tripId}/travelers", {
          params: { path: { tripId } },
          body: { name },
        }),
      ),
    onSuccess: (trip) => refreshTrip(qc, tripId, trip),
    onError,
  });
}

export function useUpdateTraveler(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ travelerId, ...body }: { travelerId: string; name?: string; color?: string }) =>
      unwrap(
        api.PATCH("/v1/trips/{tripId}/travelers/{travelerId}", {
          params: { path: { tripId, travelerId } },
          body,
        }),
      ),
    onSuccess: (trip) => refreshTrip(qc, tripId, trip),
    onError,
  });
}

export function useRemoveTraveler(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (travelerId: string) =>
      unwrap(
        api.DELETE("/v1/trips/{tripId}/travelers/{travelerId}", {
          params: { path: { tripId, travelerId } },
        }),
      ),
    onSuccess: (trip) => {
      refreshTrip(qc, tripId, trip);
      refreshActivities(qc, tripId);
    },
    onError,
  });
}

// Activity mutations

export function useAddActivity(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddActivityRequest) =>
      unwrap(api.POST("/v1/trips/{tripId}/activities", { params: { path: { tripId } }, body })),
    onSuccess: () => refreshActivities(qc, tripId),
    onError,
  });
}

export function useUpdateActivity(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, body }: { activityId: string; body: UpdateActivityRequest }) =>
      unwrap(
        api.PATCH("/v1/trips/{tripId}/activities/{activityId}", {
          params: { path: { tripId, activityId } },
          body,
        }),
      ),
    onSettled: () => refreshActivities(qc, tripId),
    onError,
  });
}

/** Status changes are optimistic: the card updates at once and rolls back on error. */
export function useSetActivityStatus(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, status }: { activityId: string; status: ActivityStatus }) =>
      unwrap(
        api.PATCH("/v1/trips/{tripId}/activities/{activityId}", {
          params: { path: { tripId, activityId } },
          body: { status },
        }),
      ),
    onMutate: ({ activityId, status }) => {
      const set = (a: Activity) => (a.id === activityId ? { ...a, status } : a);
      return optimistic(qc, tripId, (it) => mapItinerary(it, set), set);
    },
    onError: (error, _vars, snapshot) => {
      rollback(qc, snapshot);
      onError(error);
    },
    onSettled: () => refreshActivities(qc, tripId),
  });
}

/** Moves are optimistic: the card jumps to its new day at once and rolls back on error. */
export function useMoveActivity(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, body }: { activityId: string; body: MoveActivityRequest }) =>
      unwrap(
        api.POST("/v1/trips/{tripId}/activities/{activityId}/move", {
          params: { path: { tripId, activityId } },
          body,
        }),
      ),
    onMutate: ({ activityId, body }) => {
      const date = body.date ?? null;
      const moved = (a: Activity): Activity =>
        date === null
          ? { ...a, schedule: { date: null, startAt: null, endAt: null } }
          : { ...a, schedule: { ...a.schedule, date } };
      return optimistic(
        qc,
        tripId,
        (it) => {
          const all = [...it.days.flatMap((d) => d.activities), ...it.unscheduled];
          const activity = all.find((a) => a.id === activityId);
          if (!activity) return it;
          const without = (list: Activity[]) => list.filter((a) => a.id !== activityId);
          return {
            ...it,
            days: it.days.map((d) => ({
              ...d,
              activities:
                d.date === date
                  ? [...without(d.activities), moved(activity)]
                  : without(d.activities),
            })),
            unscheduled:
              date === null
                ? [...without(it.unscheduled), moved(activity)]
                : without(it.unscheduled),
          };
        },
        (a) => (a.id === activityId ? moved(a) : a),
      );
    },
    onError: (error, _vars, snapshot) => {
      rollback(qc, snapshot);
      onError(error);
    },
    onSettled: () => refreshActivities(qc, tripId),
  });
}

export function useDeleteActivity(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (activityId: string) =>
      unwrap(
        api.DELETE("/v1/trips/{tripId}/activities/{activityId}", {
          params: { path: { tripId, activityId } },
        }),
      ),
    onSuccess: () => refreshActivities(qc, tripId),
    onError,
  });
}
