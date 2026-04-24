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
  ResponsiveContainer,
} from "recharts"
import { cn } from "@/lib/utils"

interface Trade {
  edge: number
  correct: number | null
}

interface EdgeOutcomeChartProps {
  trades: Trade[]
  className?: string
}

interface EdgeBucket {
  label: string
  winRate: number
  count: number
  wins: number
  ciHalfWidth: number
  netProfit: number
}

function wilsonHalfWidth(wins: number, n: number, z = 1.96): number {
  if (n === 0) return 0
  const p = wins / n
  const denom = 1 + (z * z) / n
  const spread =
    (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
  return spread * 100
}

function spearmanRho(values: number[]): number {
  const n = values.length
  if (n < 3) return 0
  const meanRank = (n - 1) / 2
  const meanVal = values.reduce((a, b) => a + b, 0) / n
  const num = values.reduce((s, v, i) => s + (i - meanRank) * (v - meanVal), 0)
  const denA = values.reduce((s, _, i) => s + (i - meanRank) ** 2, 0)
  const denB = values.reduce((s, v) => s + (v - meanVal) ** 2, 0)
  const den = Math.sqrt(denA * denB)
  return den === 0 ? 0 : num / den
}

function computeBuckets(trades: Trade[]): EdgeBucket[] {
  const resolved = trades.filter((t) => t.correct !== null)
  const boundaries: [number, number][] = [
    [-Infinity, 0],
    [0, 0.05],
    [0.05, 0.1],
    [0.1, 0.15],
    [0.15, 0.2],
    [0.2, 0.25],
    [0.25, 0.3],
    [0.3, Infinity],
  ]
  const labels = [
    "<0%",
    "0-5%",
    "5-10%",
    "10-15%",
    "15-20%",
    "20-25%",
    "25-30%",
    "30%+",
  ]

  return boundaries.map(([lo, hi], i) => {
    const bucket = resolved.filter((t) => t.edge >= lo && t.edge < hi)
    const n = bucket.length
    const wins = bucket.filter((t) => t.correct === 1).length
    const losses = n - wins
    const winRate = n > 0 ? (wins / n) * 100 : 0
    return {
      label: labels[i],
      winRate: parseFloat(winRate.toFixed(1)),
      count: n,
      wins,
      ciHalfWidth: wilsonHalfWidth(wins, n),
      netProfit: wins - losses,
    }
  })
}

function getBarColor(winRate: number): string {
  if (winRate >= 50) return "#22c55e"
  return "#F23645"
}

type EdgeOutcomeBarProps = {
  x?: number
  y?: number
  width?: number
  height?: number
  payload?: { winRate: number; count: number; ciHalfWidth: number }
  background?: { x: number; y: number; width: number; height: number }
}

function EdgeOutcomeBar(props: EdgeOutcomeBarProps) {
  const { x, y, width, height, payload, background } = props
  if (!payload || height === undefined || x === undefined || y === undefined || width === undefined) return null

  const color = getBarColor(payload.winRate)
  const lowCount = payload.count < 5
  const barHeight = Math.max(height, 0)
  const barY = y

  const plotTop = background?.y ?? 0
  const plotBottom = (background?.y ?? 0) + (background?.height ?? 300)
  const plotHeight = plotBottom - plotTop
  const ciPx = (payload.ciHalfWidth / 100) * plotHeight
  const ciTop = Math.max(plotTop, barY - ciPx)
  const ciBottom = Math.min(plotBottom, barY + ciPx)

  return (
    <g>
      <rect
        x={x}
        y={barY}
        width={width}
        height={barHeight}
        fill={color}
        fillOpacity={0.35}
        stroke={color}
        strokeOpacity={lowCount ? 0.3 : 0.75}
        strokeWidth={1}
        strokeDasharray={lowCount ? "3 3" : undefined}
      />
      {payload.count >= 3 && ciPx > 0 && (
        <>
          <line
            x1={x + width / 2}
            y1={ciTop}
            x2={x + width / 2}
            y2={ciBottom}
            stroke="#666"
            strokeWidth={1.5}
          />
          <line
            x1={x + width / 2 - 4}
            y1={ciTop}
            x2={x + width / 2 + 4}
            y2={ciTop}
            stroke="#666"
            strokeWidth={1.5}
          />
          <line
            x1={x + width / 2 - 4}
            y1={ciBottom}
            x2={x + width / 2 + 4}
            y2={ciBottom}
            stroke="#666"
            strokeWidth={1.5}
          />
        </>
      )}
    </g>
  )
}

export function EdgeOutcomeChart({ trades, className }: EdgeOutcomeChartProps) {
  const { buckets, overallWinRate, monotonicity } = useMemo(() => {
    const b = computeBuckets(trades)
    const resolved = trades.filter((t) => t.correct !== null)
    const totalWins = resolved.filter((t) => t.correct === 1).length
    const overall =
      resolved.length > 0 ? (totalWins / resolved.length) * 100 : 50
    const nonEmptyWinRates = b.filter((bucket) => bucket.count > 0).map((bucket) => bucket.winRate)
    const rho = spearmanRho(nonEmptyWinRates)
    return {
      buckets: b,
      overallWinRate: parseFloat(overall.toFixed(1)),
      monotonicity: parseFloat(rho.toFixed(2)),
    }
  }, [trades])

  return (
    <div
      className={cn(
        "flex flex-col bg-[#0d0d0d] border border-[#242424]",
        className
      )}
    >
      <div className="flex items-center justify-between px-4 h-10 border-b border-[#242424] flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="font-mono text-[0.7rem] text-[#888] uppercase tracking-[0.12em] font-medium">
            Edge vs Outcome
          </span>
          <span className="font-mono text-[0.6rem] text-[#888]">
            monotonicity{" "}
            <span
              className={cn(
                "tabular-nums",
                monotonicity >= 0.5
                  ? "text-[#22c55e]"
                  : monotonicity >= 0.2
                    ? "text-[#e8e8e8]"
                    : "text-[#F23645]"
              )}
            >
              ρ={monotonicity}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[0.55rem]">
          <span className="text-[#888]">── 50% breakeven</span>
          <span className="text-[#38bdf8]">── avg {overallWinRate}%</span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-[#f59e0b]" />
            <span className="text-[#888]">net P&L</span>
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={buckets}
            margin={{ top: 20, right: 48, bottom: 8, left: 24 }}
            barCategoryGap="15%"
          >
            <CartesianGrid
              horizontal
              vertical={false}
              stroke="rgba(255,255,255,0.06)"
            />
            <XAxis
              dataKey="label"
              tick={(props) => {
                const { x, y, payload: tickPayload } = props as { x?: number; y?: number; payload: { value: string } }
                const bucket = buckets.find((b) => b.label === tickPayload.value)
                return (
                  <g>
                    <text
                      x={x}
                      y={y}
                      dy={4}
                      textAnchor="middle"
                      fill="#555"
                      fontFamily="var(--font-geist-mono)"
                      fontSize={10}
                    >
                      {tickPayload.value}
                    </text>
                    <text
                      x={x}
                      y={y}
                      dy={16}
                      textAnchor="middle"
                      fill="#888"
                      fontFamily="var(--font-geist-mono)"
                      fontSize={8}
                    >
                      n={bucket?.count ?? 0}
                    </text>
                  </g>
                )
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              height={36}
            />
            <YAxis
              yAxisId="left"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={(v: number) => `${v}%`}
              tick={{
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 10,
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              width={36}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{
                fill: "#f59e0b",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
              axisLine={false}
              tickLine={false}
              width={32}
            />
            <ReferenceLine
              yAxisId="left"
              y={50}
              stroke="#555"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <ReferenceLine
              yAxisId="left"
              y={overallWinRate}
              stroke="#38bdf8"
              strokeWidth={1}
              strokeDasharray="6 3"
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload as EdgeBucket
                const signal =
                  d.winRate >= 50 ? "profitable" : "unprofitable"
                const signalColor =
                  d.winRate >= 50 ? "#22c55e" : "#F23645"
                return (
                  <div className="bg-[#141414] border border-[#2a2a2a] px-3 py-2 font-mono text-xs shadow-xl">
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Edge</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.label}
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Win rate</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.winRate.toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Trades</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.wins}/{d.count}
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Net P&L</span>
                      <span
                        className={cn(
                          "tabular-nums",
                          d.netProfit >= 0
                            ? "text-[#22c55e]"
                            : "text-[#F23645]"
                        )}
                      >
                        {d.netProfit >= 0 ? "+" : ""}
                        {d.netProfit} units
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">95% CI</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        ±{d.ciHalfWidth.toFixed(1)}pp
                      </span>
                    </div>
                    <div className="flex justify-between gap-4 border-t border-[#1a1a1a] mt-1 pt-1">
                      <span className="text-[#555]">Signal</span>
                      <span style={{ color: signalColor }}>{signal}</span>
                    </div>
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
              dataKey="winRate"
              shape={<EdgeOutcomeBar />}
              isAnimationActive={false}
              maxBarSize={56}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="netProfit"
              stroke="#f59e0b"
              strokeWidth={1.5}
              dot={{ r: 3, fill: "#f59e0b", stroke: "#0d0d0d", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
