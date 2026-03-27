"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "./api"

export function useSnapshots(mode: "live" | "paper" = "paper") {
  return useQuery({
    queryKey: ["snapshots", mode],
    queryFn: () => api.snapshots(mode),
  })
}

export function usePositions(mode: "live" | "paper" = "paper") {
  return useQuery({
    queryKey: ["positions", mode],
    queryFn: () => api.positions(mode),
  })
}

export function useSignals(status: "open" | "resolved" | "all" = "all") {
  return useQuery({
    queryKey: ["signals", status],
    queryFn: () => api.signals(status),
  })
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: () => api.stats(),
  })
}

export function useCron() {
  return useQuery({
    queryKey: ["cron"],
    queryFn: () => api.cron(),
  })
}
