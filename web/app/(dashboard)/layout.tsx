"use client"

import { useState, useMemo } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { StatsStrip } from "@/components/dashboard/stats-strip"
import { useStats, useSnapshots, useSignals } from "@/lib/hooks"
import { computeDerivedMetrics } from "@/lib/metrics"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [isPaperMode, setIsPaperMode] = useState(true)
  const mode = isPaperMode ? "paper" : "live"

  const { data: statsData } = useStats()
  const { data: snapshots } = useSnapshots(mode as "live" | "paper")
  const { data: allSignals } = useSignals("all")

  // Compute NAV and daily P&L from snapshots
  const latestValue = snapshots?.length
    ? snapshots[snapshots.length - 1].value
    : 0
  const prevValue =
    snapshots && snapshots.length > 2
      ? snapshots[snapshots.length - 3].value
      : latestValue
  const dailyPnL = latestValue - prevValue
  const dailyPnLPct = prevValue > 0 ? (dailyPnL / prevValue) * 100 : 0

  // Derive advanced metrics
  const derived = useMemo(() => {
    if (!statsData || !snapshots) return null
    const resolved = (allSignals ?? []).filter((s) => s.correct !== null)
    return computeDerivedMetrics(snapshots, statsData, resolved)
  }, [statsData, snapshots, allSignals])

  const winRate = statsData?.win_rate ? Math.round(statsData.win_rate * 100) : 0
  const avgEdge = statsData?.avg_edge ? statsData.avg_edge * 100 : 0
  const openCount = statsData?.open ?? 0
  const totalTrades = statsData?.total ?? 0
  const wins = statsData?.wins ?? 0
  const losses = statsData?.losses ?? 0

  // Profit factor display
  const pf = derived?.profitFactor
  const pfDisplay =
    pf === null || pf === undefined
      ? "--"
      : pf === Infinity
        ? "∞"
        : pf.toFixed(2)
  const pfAccent: "green" | "red" | "amber" | "neutral" =
    pf === null || pf === undefined
      ? "neutral"
      : pf >= 1.5
        ? "green"
        : pf >= 1.0
          ? "amber"
          : "red"

  // Max drawdown
  const mddPct = derived?.maxDrawdownPct ?? 0
  const mddAccent: "green" | "red" | "amber" | "neutral" =
    mddPct > 0.15 ? "red" : mddPct > 0.08 ? "amber" : "neutral"

  // Sharpe
  const sharpe = derived?.sharpeRatio
  const sharpeDisplay = sharpe !== null && sharpe !== undefined ? sharpe.toFixed(2) : "--"
  const sharpeAccent: "green" | "red" | "amber" | "neutral" =
    sharpe === null || sharpe === undefined
      ? "neutral"
      : sharpe >= 1.0
        ? "green"
        : sharpe >= 0.5
          ? "amber"
          : "red"

  const groups = [
    {
      label: "Activity",
      cards: [
        {
          label: "Open Positions",
          value: String(openCount),
          accent: "neutral" as const,
        },
        {
          label: "Total Trades",
          value: String(totalTrades),
          accent: "neutral" as const,
          delta:
            wins + losses > 0
              ? {
                  value: `${wins}W / ${losses}L`,
                  direction: "flat" as const,
                }
              : undefined,
        },
      ],
    },
    {
      label: "Performance",
      cards: [
        {
          label: "Win Rate",
          value: `${winRate}%`,
          accent: "neutral" as const,
          delta:
            winRate > 0
              ? {
                  value: winRate > 50 ? "above 50%" : "below 50%",
                  direction: (winRate > 50 ? "up" : "down") as "up" | "down",
                }
              : undefined,
          sparkline: derived?.winRateSeries,
          sparklineColor: winRate >= 50 ? "#22c55e" : "#ef4444",
          sparklineRef: 0.5,
        },
        {
          label: "Expectancy",
          value: `${avgEdge > 0 ? "+" : ""}${avgEdge.toFixed(1)}%`,
          accent: (avgEdge > 0 ? "green" : avgEdge < 0 ? "red" : "neutral") as
            | "green"
            | "red"
            | "neutral",
        },
        {
          label: "Profit Factor",
          value: pfDisplay,
          accent: pfAccent,
        },
      ],
    },
    {
      label: "Risk",
      cards: [
        {
          label: "Max Drawdown",
          value: `\u2212${(mddPct * 100).toFixed(1)}%`,
          accent: mddAccent,
          thresholdBar: { current: mddPct, max: 0.20 },
        },
        {
          label: "Sharpe Ratio",
          value: sharpeDisplay,
          accent: sharpeAccent,
          thresholdBar: {
            current: sharpe !== null && sharpe !== undefined ? Math.abs(sharpe) : 0,
            max: 5.0,
          },
        },
      ],
    },
  ]

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar
        isPaperMode={isPaperMode}
        onModeToggle={setIsPaperMode}
      />
      <StatsStrip groups={groups} />
      <main className="flex-1 px-4 py-3 flex flex-col gap-3">{children}</main>
    </div>
  )
}
