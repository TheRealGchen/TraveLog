"use client";

import type {
  Activity,
  ActivityStatus,
  AddActivityRequest,
  CreateTripRequest,
  Day,
  DayList,
  MoveActivityRequest,
  Trip,
  UpdateActivityRequest,
  UpdateDayRequest,
  UpdateTripRequest,
} from "@travel/client";
import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, errorMessage, unwrap } from "./api";

/** Poll open trip views so edits made by agents through the API show up. */
const POLL_MS = 10_000;

export interface ActivityFilters {
  status?: ActivityStatus;
  travelerId?: string;
}

export const keys = {
  trips: ["trips"] as const,
  trip: (tripId: string) => ["trip", tripId] as const,
  days: (tripId: string) => ["days", tripId] as const,
  day: (tripId: string, date?: string) =>
    date ? (["day", tripId, date] as const) : (["day", tripId] as const),
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

export function useDays(tripId: string) {
  return useQuery({
    queryKey: keys.days(tripId),
    queryFn: () => unwrap(api.GET("/v1/trips/{tripId}/days", { params: { path: { tripId } } })),
    refetchInterval: POLL_MS,
  });
}

export function useDay(tripId: string, date: string) {
  return useQuery({
    queryKey: keys.day(tripId, date),
    queryFn: () =>
      unwrap(api.GET("/v1/trips/{tripId}/days/{date}", { params: { path: { tripId, date } } })),
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
}

/** Refetch every cached view of the trip's days and activities. */
function refreshDays(qc: QueryClient, tripId: string) {
  void qc.invalidateQueries({ queryKey: keys.days(tripId) });
  void qc.invalidateQueries({ queryKey: keys.day(tripId) });
  void qc.invalidateQueries({ queryKey: keys.activities(tripId) });
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
      refreshDays(qc, tripId);
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
    onSuccess: (trip) => {
      refreshTrip(qc, tripId, trip);
      refreshDays(qc, tripId);
    },
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
    onSuccess: (trip) => {
      refreshTrip(qc, tripId, trip);
      refreshDays(qc, tripId);
    },
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
      refreshDays(qc, tripId);
    },
    onError,
  });
}

// Day mutations

export function useUpdateDay(tripId: string, date: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateDayRequest) =>
      unwrap(
        api.PATCH("/v1/trips/{tripId}/days/{date}", { params: { path: { tripId, date } }, body }),
      ),
    onSuccess: (day) => {
      qc.setQueryData(keys.day(tripId, date), day);
      void qc.invalidateQueries({ queryKey: keys.days(tripId) });
    },
    onError,
  });
}

// Activity mutations

export function useAddActivity(tripId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ date, body }: { date: string; body: AddActivityRequest }) =>
      unwrap(
        api.POST("/v1/trips/{tripId}/days/{date}/activities", {
          params: { path: { tripId, date } },
          body,
        }),
      ),
    onSuccess: () => refreshDays(qc, tripId),
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
    onSettled: () => refreshDays(qc, tripId),
    onError,
  });
}

type Snapshot = [readonly unknown[], unknown][];

/** Status changes are optimistic: every cached copy updates at once, rolling back on error. */
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
    onMutate: async ({ activityId, status }): Promise<Snapshot> => {
      const filters = [keys.days(tripId), keys.day(tripId), keys.activities(tripId)];
      await Promise.all(filters.map((queryKey) => qc.cancelQueries({ queryKey })));
      const snapshot = filters.flatMap((queryKey) => qc.getQueriesData({ queryKey }));
      const set = (list: Activity[]) =>
        list.map((a) => (a.id === activityId ? { ...a, status } : a));
      qc.setQueryData<DayList>(keys.days(tripId), (d) =>
        d && { ...d, days: d.days.map((day) => ({ ...day, activities: set(day.activities) })) },
      );
      qc.setQueriesData<Day>({ queryKey: keys.day(tripId) }, (day) =>
        day && { ...day, activities: set(day.activities) },
      );
      qc.setQueriesData<{ activities: Activity[] }>({ queryKey: keys.activities(tripId) }, (l) =>
        l && { activities: set(l.activities) },
      );
      return snapshot;
    },
    onError: (error, _vars, snapshot) => {
      for (const [key, data] of snapshot ?? []) qc.setQueryData(key, data);
      onError(error);
    },
    onSettled: () => refreshDays(qc, tripId),
  });
}

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
    onSettled: () => refreshDays(qc, tripId),
    onError,
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
    onSuccess: () => refreshDays(qc, tripId),
    onError,
  });
}
