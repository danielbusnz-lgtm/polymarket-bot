"use client"

import { useRef, useEffect, useState } from "react"
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"
import { cn } from "@/lib/utils"

interface CalibrationBucket {
  x: number
  y: number
  count: number
}

interface CalibrationChartProps {
  data: CalibrationBucket[]
  className?: string
}

// We render two scatter series:
// 1. Invisible points at (x, x) to capture diagonal pixel positions
// 2. Visible points at (x, y) with custom shape that draws the gap bar

function CalibrationTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: CalibrationBucket }[]
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  if (!("count" in d)) return null // skip diagonal points
  const error = d.y - d.x
  const direction =
    error > 0 ? "underconfident" : error < 0 ? "overconfident" : "perfect"

  return (
    <div className="bg-[#141414] border border-[#2a2a2a] px-3 py-2 font-mono text-xs shadow-xl">
      <div className="flex justify-between gap-4">
        <span className="text-[#555]">Predicted</span>
        <span className="text-[#e8e8e8] tabular-nums">
          {(d.x * 100).toFixed(0)}%
        </span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-[#555]">Actual</span>
        <span className="text-[#e8e8e8] tabular-nums">
          {(d.y * 100).toFixed(1)}%
        </span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-[#555]">Samples</span>
        <span className="text-[#e8e8e8] tabular-nums">{d.count}</span>
      </div>
      <div className="flex justify-between gap-4 border-t border-[#1a1a1a] mt-1 pt-1">
        <span className="text-[#555]">Error</span>
        <span
          className={cn(
            "tabular-nums",
            Math.abs(error) < 0.03 ? "text-[#22c55e]" : "text-amber-400"
          )}
        >
          {error > 0 ? "+" : ""}
          {(error * 100).toFixed(1)}pp {direction}
        </span>
      </div>
    </div>
  )
}

export function CalibrationChart({ data, className }: CalibrationChartProps) {
  const diagonalPixels = useRef<Map<number, number>>(new Map())

  // Diagonal points: same x mapped to y axis to capture pixel positions
  const diagonalData = data.map((d) => ({ x: d.x, y: d.x }))

  const countByX = new Map(data.map((d) => [Math.round(d.x * 100), d.count]))

  return (
    <div
      className={cn(
        "flex flex-col bg-[#0d0d0d] border border-[#242424]",
        className
      )}
    >
      <div className="flex items-center justify-between px-4 h-10 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.7rem] text-[#888] uppercase tracking-[0.12em] font-medium">
            Calibration
          </span>
          <span className="flex items-center gap-1.5 font-mono text-[0.55rem]">
            <span className="inline-block w-2 h-2 bg-emerald-500/40 border border-emerald-500/60" />
            <span className="text-[#888]">underconfident</span>
            <span className="inline-block w-2 h-2 bg-[#F23645]/40 border border-[#F23645]/60 ml-2" />
            <span className="text-[#888]">overconfident</span>
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 24, bottom: 8, left: 24 }}>
            <CartesianGrid
              horizontal
              vertical={false}
              stroke="rgba(255,255,255,0.06)"
            />
            <XAxis
              type="number"
              dataKey="x"
              domain={[0, 1]}
              ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]}
              tick={(props: { x?: number; y?: number; payload: { value: number } }) => {
                const { x, y, payload } = props
                const pctVal = Math.round(payload.value * 100)
                const count = countByX.get(pctVal)
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
                      {pctVal}%
                    </text>
                    {count !== undefined && (
                      <text
                        x={x}
                        y={y}
                        dy={16}
                        textAnchor="middle"
                        fill="#888"
                        fontFamily="var(--font-geist-mono)"
                        fontSize={8}
                      >
                        n={count}
                      </text>
                    )}
                  </g>
                )
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              height={36}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1.0]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              tick={{
                fill: "#555",
                fontFamily: "var(--font-geist-mono)",
                fontSize: 10,
              }}
              axisLine={{ stroke: "#1a1a1a" }}
              tickLine={false}
              width={45}
            />
            <ReferenceLine
              segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
              stroke="#444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <Tooltip
              content={<CalibrationTooltip />}
              cursor={{
                stroke: "rgba(255,255,255,0.1)",
                strokeDasharray: "3 3",
              }}
              wrapperStyle={{ outline: "none", filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.6))", zIndex: 50 }}
            />
            {/* Invisible diagonal scatter to capture pixel positions */}
            <Scatter
              data={diagonalData}
              fill="transparent"
              shape={(props: { cx?: number; cy?: number; payload: { x: number } }) => {
                if (props.cx && props.cy) {
                  diagonalPixels.current.set(props.payload.x, props.cy)
                }
                return <circle cx={0} cy={0} r={0} />
              }}
            />
            {/* Visible data points with gap bars */}
            <Scatter
              data={data}
              fill="transparent"
              shape={(props: { cx?: number; cy?: number; payload: { x: number; y: number } }) => {
                const { cx, cy, payload } = props
                if (!cx || !cy) return null

                const diagY = diagonalPixels.current.get(payload.x)
                if (diagY === undefined) return null

                const isOverconfident = payload.y < payload.x
                const lineColor = isOverconfident
                  ? "#F23645"
                  : "#22c55e"
                const dotFill = isOverconfident ? "#F23645" : "#22c55e"

                return (
                  <g>
                    <line
                      x1={cx}
                      y1={diagY}
                      x2={cx}
                      y2={cy}
                      stroke={lineColor}
                      strokeWidth={2.5}
                      strokeOpacity={0.8}
                    />
                    <circle
                      cx={cx}
                      cy={cy}
                      r={4}
                      fill={dotFill}
                      fillOpacity={0.85}
                      stroke={dotFill}
                      strokeWidth={1.5}
                    />
                  </g>
                )
              }}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

    </div>
  )
}
