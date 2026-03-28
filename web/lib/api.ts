import type { PortfolioSnapshot, Position, Signal, Stats, CronInfo } from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8888"

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  snapshots: async (mode: "live" | "paper" = "paper") => {
    const res = await get<{ mode: string; snapshots: PortfolioSnapshot[] }>(
      `/api/snapshots?mode=${mode}`
    )
    return res.snapshots
  },

  positions: async (mode: "live" | "paper" = "paper") => {
    const res = await get<{ mode: string; positions: Position[] }>(
      `/api/positions?mode=${mode}`
    )
    return res.positions
  },

  signals: async (status: "open" | "resolved" | "all" = "all") => {
    const res = await get<{ status: string; signals: Signal[] }>(
      `/api/signals?status=${status}`
    )
    return res.signals
  },

  stats: () => get<Stats>("/api/stats"),

  cron: () => get<CronInfo>("/api/cron"),

  prices: async (tokenIds: string[]) => {
    if (tokenIds.length === 0) return {}
    const res = await get<{ prices: Record<string, number> }>(
      `/api/prices?token_ids=${tokenIds.join(",")}`
    )
    return res.prices
  },
}
