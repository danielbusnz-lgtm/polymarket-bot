"use client"

import { useMemo } from "react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"
import { cn } from "@/lib/utils"

interface Trade {
  disagreement: number
  correct: number | null
}

interface DisagreementAccuracyChartProps {
  trades: Trade[]
  className?: string
}

interface DisagreementBucket {
  label: string
  winRate: number
  count: number
  wins: number
  ciHalfWidth: number
}

function wilsonHalfWidth(wins: number, n: number, z = 1.96): number {
  if (n === 0) return 0
  const p = wins / n
  const denom = 1 + (z * z) / n
  const spread =
    (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
  return spread * 100
}

function pearsonR(xs: number[], ys: number[]): number {
  const n = xs.length
  if (n < 3) return 0
  const mx = xs.reduce((s, v) => s + v, 0) / n
  const my = ys.reduce((s, v) => s + v, 0) / n
  let num = 0
  let dx2 = 0
  let dy2 = 0
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx
    const dy = ys[i] - my
    num += dx * dy
    dx2 += dx * dx
    dy2 += dy * dy
  }
  const denom = Math.sqrt(dx2 * dy2)
  return denom === 0 ? 0 : num / denom
}

function computeBuckets(trades: Trade[]): DisagreementBucket[] {
  const resolved = trades.filter((t) => t.correct !== null)
  const boundaries: [number, number][] = [
    [0, 0.05],
    [0.05, 0.10],
    [0.10, 0.15],
    [0.15, 0.20],
    [0.20, 0.25],
  ]
  const labels = ["0-5%", "5-10%", "10-15%", "15-20%", "20-25%"]

  return boundaries.map(([lo, hi], i) => {
    const bucket = resolved.filter((t) => t.disagreement >= lo && t.disagreement < hi)
    const n = bucket.length
    const wins = bucket.filter((t) => t.correct === 1).length
    const winRate = n > 0 ? (wins / n) * 100 : 0
    return {
      label: labels[i],
      winRate: parseFloat(winRate.toFixed(1)),
      count: n,
      wins,
      ciHalfWidth: wilsonHalfWidth(wins, n),
    }
  })
}

function DisagreementBar(props: any) {
  const { x, y, width, height, payload, overallWinRate, background } = props
  if (!payload || height === undefined) return null

  const color = payload.winRate >= overallWinRate ? "#22c55e" : "#F23645"
  const lowCount = payload.count < 5
  const barHeight = Math.max(height, 0)

  const plotTop = background?.y ?? 0
  const plotBottom = (background?.y ?? 0) + (background?.height ?? 300)
  const plotHeight = plotBottom - plotTop
  const ciPx = (payload.ciHalfWidth / 100) * plotHeight
  const ciTop = Math.max(plotTop, y - ciPx)
  const ciBottom = Math.min(plotBottom, y + ciPx)

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={barHeight}
        fill={color}
        fillOpacity={0.35}
        stroke={color}
        strokeOpacity={lowCount ? 0.3 : 0.7}
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

export function DisagreementAccuracyChart({
  trades,
  className,
}: DisagreementAccuracyChartProps) {
  const { buckets, overallWinRate, correlation, meanDisagreement } =
    useMemo(() => {
      const b = computeBuckets(trades)
      const resolved = trades.filter((t) => t.correct !== null)
      const totalWins = resolved.filter((t) => t.correct === 1).length
      const overall =
        resolved.length > 0 ? (totalWins / resolved.length) * 100 : 50
      const rho = pearsonR(
        resolved.map((t) => t.disagreement),
        resolved.map((t) => t.correct as number)
      )
      const meanD =
        resolved.length > 0
          ? resolved.reduce((s, t) => s + t.disagreement, 0) / resolved.length
          : 0
      return {
        buckets: b,
        overallWinRate: parseFloat(overall.toFixed(1)),
        correlation: parseFloat(rho.toFixed(2)),
        meanDisagreement: parseFloat((meanD * 100).toFixed(1)),
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
        <span className="font-mono text-[0.7rem] text-[#888] uppercase tracking-[0.12em] font-medium">
          Disagreement vs Accuracy
        </span>
        <div className="flex items-center gap-4 font-mono text-[0.6rem]">
          <span className="text-[#888]">
            ρ{" "}
            <span
              className={cn(
                "tabular-nums",
                correlation < -0.1
                  ? "text-[#22c55e]"
                  : correlation > 0.1
                    ? "text-[#F23645]"
                    : "text-[#e8e8e8]"
              )}
            >
              {correlation > 0 ? "+" : ""}
              {correlation}
            </span>
          </span>
          <span className="text-[#888]">
            μ <span className="text-[#e8e8e8] tabular-nums">{meanDisagreement}%</span>
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={buckets}
            margin={{ top: 20, right: 24, bottom: 8, left: 24 }}
            barCategoryGap="15%"
          >
            <CartesianGrid
              horizontal
              vertical={false}
              stroke="rgba(255,255,255,0.06)"
            />
            <XAxis
              dataKey="label"
              tick={(props: any) => {
                const { x, y, payload: tickPayload } = props
                const bucket = buckets.find((b: any) => b.label === tickPayload.value)
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
            <ReferenceLine
              y={overallWinRate}
              stroke="#38bdf8"
              strokeWidth={1}
              strokeDasharray="6 3"
              label={{
                value: `avg ${overallWinRate}%`,
                position: "insideTopRight",
                fill: "#38bdf8",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
            />
            <ReferenceLine
              x="15-20%"
              stroke="#f59e0b"
              strokeWidth={1}
              strokeDasharray="4 2"
              label={{
                value: "filter",
                position: "insideTopLeft",
                fill: "#f59e0b",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload as DisagreementBucket
                const diff = d.winRate - overallWinRate
                const signal =
                  diff >= 0 ? "above avg" : "below avg"
                const signalColor =
                  diff >= 0 ? "#22c55e" : "#F23645"
                return (
                  <div className="bg-[#141414] border border-[#2a2a2a] px-3 py-2 font-mono text-xs shadow-xl">
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Disagreement</span>
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
                      <span className="text-[#555]">95% CI</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        ±{d.ciHalfWidth.toFixed(1)}pp
                      </span>
                    </div>
                    <div className="flex justify-between gap-4 border-t border-[#1a1a1a] mt-1 pt-1">
                      <span className="text-[#555]">vs avg</span>
                      <span style={{ color: signalColor }}>
                        {diff >= 0 ? "+" : ""}
                        {diff.toFixed(1)}pp {signal}
                      </span>
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
              dataKey="winRate"
              shape={(props: any) => (
                <DisagreementBar {...props} overallWinRate={overallWinRate} />
              )}
              isAnimationActive={false}
              maxBarSize={56}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
