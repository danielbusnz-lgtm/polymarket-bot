"use client"

import { useMemo } from "react"
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Cell,
} from "recharts"
import { cn } from "@/lib/utils"

interface Trade {
  edge: number
  correct: number | null
}

interface EdgeHistogramProps {
  trades: Trade[]
  className?: string
}

const MIN_EDGE = 0.12
const TARGET_HI = 0.25

const BIN_EDGES = [
  -0.05, -0.025, 0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20,
  0.225, 0.25, 0.275, 0.30, 0.325, 0.35,
]

function binData(trades: Trade[]) {
  return BIN_EDGES.slice(0, -1).map((low, i) => {
    const high = BIN_EDGES[i + 1]
    const mid = (low + high) / 2
    const inBin = trades.filter((t) => t.edge >= low && t.edge < high)
    const resolved = inBin.filter((t) => t.correct !== null)
    const wins = resolved.filter((t) => t.correct === 1).length
    const winRate = resolved.length >= 5 ? (wins / resolved.length) * 100 : null
    return {
      label: `${Math.round(mid * 100)}%`,
      rangeLabel: `${Math.round(low * 100)}% to ${Math.round(high * 100)}%`,
      midpoint: mid,
      count: inBin.length,
      resolvedCount: resolved.length,
      wins,
      winRate,
      isNegative: mid < 0,
      isBelowThreshold: mid >= 0 && mid < MIN_EDGE,
    }
  })
}

function getBarColor(entry: { isNegative: boolean; isBelowThreshold: boolean }) {
  if (entry.isNegative) return "#F23645"
  if (entry.isBelowThreshold) return "#f59e0b"
  return "#22c55e"
}

// Target zone bin labels (12.5% through 25%)
const TARGET_LO_LABEL = "13%"
const TARGET_HI_LABEL = "24%"

export function EdgeHistogram({ trades, className }: EdgeHistogramProps) {
  const { chartData, meanEdge, medianEdge, belowCount, recentMean, recentDelta } =
    useMemo(() => {
      const edges = trades.map((t) => t.edge)
      const sorted = [...edges].sort((a, b) => a - b)
      const mean = sorted.reduce((s, v) => s + v, 0) / (sorted.length || 1)
      const midIdx = Math.floor(sorted.length / 2)
      const median =
        sorted.length === 0
          ? 0
          : sorted.length % 2
            ? sorted[midIdx]
            : (sorted[midIdx - 1] + sorted[midIdx]) / 2
      const below = sorted.filter((e) => e >= 0 && e < MIN_EDGE).length
      const cd = binData(trades)

      // Temporal drift: last 100 trades vs all
      const recentN = Math.min(100, trades.length)
      const recentEdges = trades.slice(-recentN).map((t) => t.edge)
      const rMean = recentEdges.reduce((s, v) => s + v, 0) / (recentEdges.length || 1)
      const delta = rMean - mean

      return {
        chartData: cd,
        meanEdge: mean,
        medianEdge: median,
        belowCount: below,
        recentMean: rMean,
        recentDelta: delta,
      }
    }, [trades])

  const meanBinLabel = chartData.reduce((closest, bin) =>
    Math.abs(bin.midpoint - meanEdge) < Math.abs(closest.midpoint - meanEdge)
      ? bin
      : closest
  ).label

  const driftColor =
    recentDelta < -0.02 ? "text-[#F23645]" : recentDelta > 0.02 ? "text-[#22c55e]" : "text-[#e8e8e8]"
  const driftArrow = recentDelta >= 0 ? "↑" : "↓"

  return (
    <div
      className={cn(
        "flex flex-col bg-[#0d0d0d] border border-[#242424]",
        className
      )}
    >
      <div className="flex items-center justify-between px-4 h-10 border-b border-[#242424] flex-shrink-0">
        <span className="font-mono text-[0.7rem] text-[#888] uppercase tracking-[0.12em] font-medium">
          Edge Distribution
        </span>
        <div className="flex items-center gap-3 font-mono text-[0.6rem]">
          <span className="text-[#888]">
            μ <span className="text-[#e8e8e8] tabular-nums">{(meanEdge * 100).toFixed(1)}%</span>
          </span>
          <span className="text-[#888]">
            recent{" "}
            <span className={cn("tabular-nums", driftColor)}>
              {(recentMean * 100).toFixed(1)}% {driftArrow}{" "}
              {recentDelta >= 0 ? "+" : ""}
              {(recentDelta * 100).toFixed(1)}pp
            </span>
          </span>
          {belowCount > 0 && (
            <span className="text-amber-400">{belowCount} below min</span>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 20, right: 24, bottom: 8, left: 24 }}
            barCategoryGap={0}
            barGap={0}
          >
            {/* Target zone shading */}
            <ReferenceArea
              x1={TARGET_LO_LABEL}
              x2={TARGET_HI_LABEL}
              fill="#22c55e"
              fillOpacity={0.04}
              stroke="none"
            />
            <CartesianGrid
              horizontal
              vertical={false}
              stroke="rgba(255,255,255,0.06)"
            />
            <XAxis
              dataKey="label"
              tick={{
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 10,
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              interval={1}
            />
            <YAxis
              yAxisId="left"
              hide
            />
            <ReferenceLine
              yAxisId="left"
              x="0%"
              stroke="#555"
              strokeWidth={1}
              strokeDasharray="3 3"
              label={{
                value: "0%",
                position: "insideTopRight",
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
            />
            <ReferenceLine
              yAxisId="left"
              x="13%"
              stroke="#f59e0b"
              strokeWidth={1}
              strokeDasharray="4 2"
              label={{
                value: "min",
                position: "insideTopRight",
                fill: "#f59e0b",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
            />
            <ReferenceLine
              yAxisId="left"
              x={meanBinLabel}
              stroke="#555"
              strokeWidth={1}
              strokeDasharray="6 3"
              label={{
                value: "μ",
                position: "insideTopRight",
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                const total = trades.length
                const pct =
                  total > 0 ? ((d.count / total) * 100).toFixed(1) : "0"
                return (
                  <div className="bg-[#141414] border border-[#2a2a2a] px-3 py-2 font-mono text-xs shadow-xl">
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Range</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.rangeLabel}
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Count</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.count}
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Share</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {pct}%
                      </span>
                    </div>
                    {d.winRate !== null && (
                      <div className="flex justify-between gap-4 border-t border-[#1a1a1a] mt-1 pt-1">
                        <span className="text-[#555]">Win rate</span>
                        <span
                          className={cn(
                            "tabular-nums",
                            d.winRate >= 60
                              ? "text-[#22c55e]"
                              : d.winRate >= 50
                                ? "text-[#e8e8e8]"
                                : "text-[#F23645]"
                          )}
                        >
                          {d.winRate.toFixed(1)}% ({d.wins}/{d.resolvedCount})
                        </span>
                      </div>
                    )}
                    {d.winRate === null && d.resolvedCount > 0 && (
                      <div className="flex justify-between gap-4 border-t border-[#1a1a1a] mt-1 pt-1">
                        <span className="text-[#555]">Win rate</span>
                        <span className="text-[#444]">
                          too few trades ({d.resolvedCount})
                        </span>
                      </div>
                    )}
                  </div>
                )
              }}
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              wrapperStyle={{
                outline: "none",
                filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.6))",
                zIndex: 50,
              }}
            />
            <Bar
              yAxisId="left"
              dataKey="count"
              radius={0}
              isAnimationActive={false}
            >
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={getBarColor(entry)}
                  fillOpacity={0.35}
                  stroke={getBarColor(entry)}
                  strokeOpacity={0.75}
                  strokeWidth={1}
                />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
