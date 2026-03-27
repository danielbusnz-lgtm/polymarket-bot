"use client"

import { useMemo } from "react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts"
import { cn } from "@/lib/utils"

interface Trade {
  run_at: string
  correct: number | null
}

interface RollingWinRateProps {
  trades: Trade[]
  window?: number
  className?: string
}

interface RollingPoint {
  tradeIndex: number
  runAt: string
  rollingWinRate: number
  correct: number
}

function computeRollingData(trades: Trade[], window: number): RollingPoint[] {
  const resolved = trades.filter((t) => t.correct !== null)
  if (resolved.length < window) return []

  return resolved.slice(window - 1).map((_, i) => {
    const slice = resolved.slice(i, i + window)
    const wins = slice.filter((t) => t.correct === 1).length
    return {
      tradeIndex: i + window,
      runAt: resolved[i + window - 1].run_at,
      rollingWinRate: parseFloat(((wins / window) * 100).toFixed(1)),
      correct: resolved[i + window - 1].correct as number,
    }
  })
}

function computeTrend(points: RollingPoint[], lookback: number): number {
  if (points.length < lookback) return 0
  const recent = points.slice(-lookback)
  const n = recent.length
  const sumX = recent.reduce((s, _, i) => s + i, 0)
  const sumY = recent.reduce((s, p) => s + p.rollingWinRate, 0)
  const sumXY = recent.reduce((s, p, i) => s + i * p.rollingWinRate, 0)
  const sumX2 = recent.reduce((s, _, i) => s + i * i, 0)
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX)
  return parseFloat((slope * lookback).toFixed(1))
}

function WinRateDot(props: { cx: number; cy: number; payload: RollingPoint }) {
  const { cx, cy, payload } = props
  if (!cx || !cy) return null
  const isWin = payload.correct === 1
  return (
    <circle
      cx={cx}
      cy={cy}
      r={isWin ? 2.5 : 2}
      fill={isWin ? "#22c55e" : "#F23645"}
      fillOpacity={isWin ? 0.7 : 0.5}
    />
  )
}

export function RollingWinRate({
  trades,
  window = 20,
  className,
}: RollingWinRateProps) {
  const { points, currentRate, overallRate, trend } = useMemo(() => {
    const pts = computeRollingData(trades, window)
    const current = pts.length > 0 ? pts[pts.length - 1].rollingWinRate : null
    const resolved = trades.filter((t) => t.correct !== null)
    const totalWins = resolved.filter((t) => t.correct === 1).length
    const overall =
      resolved.length > 0
        ? parseFloat(((totalWins / resolved.length) * 100).toFixed(1))
        : 0
    const trendVal = computeTrend(pts, 10)
    return { points: pts, currentRate: current, overallRate: overall, trend: trendVal }
  }, [trades, window])

  const trendPositive = trend >= 0
  const resolved = trades.filter((t) => t.correct !== null).length

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
            Rolling Win Rate
          </span>
          {currentRate !== null && (
            <>
              <span className="font-mono text-lg font-bold tabular-nums text-[#e8e8e8]">
                {currentRate}%
              </span>
              <span
                className={cn(
                  "font-mono text-xs font-medium tabular-nums",
                  trendPositive ? "text-[#22c55e]" : "text-[#F23645]"
                )}
              >
                {trendPositive ? "↑" : "↓"} {trendPositive ? "+" : ""}
                {trend}pp
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-4 font-mono text-[0.6rem]">
          <span className="text-[#888]">{window}-trade window</span>
          <span className="text-[#888]">n={resolved} resolved</span>
          <span className="text-[#888]">── 50% breakeven</span>
          <span className="text-[#38bdf8]">── avg {overallRate}%</span>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={points}
            margin={{ top: 16, right: 24, bottom: 8, left: 24 }}
            accessibilityLayer={false}
          >
            <defs>
              <linearGradient id="winRateFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.20} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="winRateStroke" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#22c55e" />
                <stop offset="50%" stopColor="#22c55e" />
                <stop offset="50%" stopColor="#F23645" />
                <stop offset="100%" stopColor="#F23645" />
              </linearGradient>
            </defs>
            <ReferenceArea
              y1={0}
              y2={50}
              fill="rgba(242,54,69,0.04)"
              stroke="none"
            />
            <CartesianGrid
              horizontal
              vertical={false}
              stroke="rgba(255,255,255,0.06)"
            />
            <XAxis
              dataKey="tradeIndex"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 10,
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              label={{
                value: "Trade #",
                position: "bottom",
                offset: 0,
                fill: "#333",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 9,
              }}
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
            <Area
              type="monotone"
              dataKey="rollingWinRate"
              stroke="url(#winRateStroke)"
              strokeWidth={2}
              fill="url(#winRateFill)"
              fillOpacity={1}
              dot={<WinRateDot cx={0} cy={0} payload={{ tradeIndex: 0, runAt: "", rollingWinRate: 0, correct: 0 }} />}
              isAnimationActive={false}
            />
            <ReferenceLine
              y={50}
              stroke="#555"
              strokeDasharray="3 3"
              strokeWidth={1}
            />
            <ReferenceLine
              y={overallRate}
              stroke="#38bdf8"
              strokeDasharray="6 3"
              strokeWidth={1}
              strokeOpacity={0.5}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload as RollingPoint
                return (
                  <div className="bg-[#141414] border border-[#2a2a2a] px-3 py-2 font-mono text-xs shadow-xl">
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Trade</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        #{d.tradeIndex}
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Win rate</span>
                      <span className="text-[#e8e8e8] tabular-nums">
                        {d.rollingWinRate}%
                      </span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-[#555]">Last trade</span>
                      <span
                        className={cn(
                          "tabular-nums",
                          d.correct === 1
                            ? "text-[#22c55e]"
                            : "text-[#F23645]"
                        )}
                      >
                        {d.correct === 1 ? "WIN" : "LOSS"}
                      </span>
                    </div>
                  </div>
                )
              }}
              cursor={{
                stroke: "rgba(255,255,255,0.1)",
                strokeDasharray: "3 3",
              }}
              wrapperStyle={{
                outline: "none",
                filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.6))",
                zIndex: 50,
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
