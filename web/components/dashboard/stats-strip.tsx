"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

/* ------------------------------------------------------------------ */
/*  Value flash hook                                                    */
/* ------------------------------------------------------------------ */

function useValueFlash(value: string): "up" | "down" | null {
  const prevRef = useRef(value)
  const [flash, setFlash] = useState<"up" | "down" | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = value

    if (prev === value) return

    // Parse numeric portions to determine direction
    const prevNum = parseFloat(prev.replace(/[^0-9.\-]/g, ""))
    const currNum = parseFloat(value.replace(/[^0-9.\-]/g, ""))

    if (isNaN(prevNum) || isNaN(currNum) || prevNum === currNum) return

    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: animated flash on prop change
    setFlash(currNum > prevNum ? "up" : "down")

    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setFlash(null), 400)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [value])

  return flash
}

/* ------------------------------------------------------------------ */
/*  Sparkline                                                          */
/* ------------------------------------------------------------------ */

function Sparkline({
  data,
  color,
  refValue,
  width = 80,
  height = 28,
}: {
  data: number[]
  color: string
  refValue?: number
  width?: number
  height?: number
}) {
  if (data.length < 2) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const pad = 4 // inset so endpoint dot doesn't clip the SVG edge

  const coords = data.map((v, i) => ({
    x: pad + (i / (data.length - 1)) * (width - pad * 2),
    y: height - ((v - min) / range) * (height - 4) - 2,
  }))

  const linePoints = coords.map((c) => `${c.x},${c.y}`).join(" ")

  // Closed polygon: trace the line, then drop to bottom-right, bottom-left
  const areaPoints =
    linePoints + ` ${coords[coords.length - 1].x},${height} ${coords[0].x},${height}`

  const lastPt = coords[coords.length - 1]

  // Unique gradient ID per instance to avoid SVG ID collisions
  const gradId = `spark-fill-${color.replace("#", "")}`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="mt-1"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.25} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>

      {/* Reference line (e.g. 50% for win rate, 1.0 for profit factor) */}
      {refValue !== undefined && refValue >= min && refValue <= max && (
        <line
          x1={0}
          y1={height - ((refValue - min) / range) * (height - 4) - 2}
          x2={width}
          y2={height - ((refValue - min) / range) * (height - 4) - 2}
          stroke="#334155"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      )}

      {/* Area fill */}
      <polygon
        points={areaPoints}
        fill={`url(#${gradId})`}
      />

      {/* Line */}
      <polyline
        points={linePoints}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Current-value endpoint dot */}
      <circle cx={lastPt.x} cy={lastPt.y} r={3} fill={color} />
    </svg>
  )
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Accent = "green" | "red" | "amber" | "neutral"

interface KpiCard {
  label: string
  value: string
  accent: Accent
  delta?: { value: string; direction: "up" | "down" | "flat" }
  sparkline?: number[]
  sparklineColor?: string
  sparklineRef?: number
  /** Threshold bar: fill is current/max, clamped to 0-1. Color follows accent. */
  thresholdBar?: { current: number; max: number }
}

interface KpiGroup {
  label: string
  cards: KpiCard[]
}

export interface StatsStripProps {
  groups: KpiGroup[]
  className?: string
}

/* ------------------------------------------------------------------ */
/*  Accent color map                                                   */
/* ------------------------------------------------------------------ */

const ACCENT_COLOR: Record<Accent, string> = {
  green: "#22c55e",
  red: "#ef4444",
  amber: "#f59e0b",
  neutral: "#e2e8f0",
}

/* ------------------------------------------------------------------ */
/*  Single KPI card (extracted so hooks are valid)                      */
/* ------------------------------------------------------------------ */

function KpiCardCell({
  card,
  showSeparator,
}: {
  card: KpiCard
  showSeparator: boolean
}) {
  const flash = useValueFlash(card.value)

  return (
    <div
      className={cn(
        "flex flex-1 flex-col px-4 pb-2.5 pt-1 min-w-0",
        showSeparator && "border-r border-[#1a1a1a]",
        flash === "up" && "kpi-flash-up",
        flash === "down" && "kpi-flash-down"
      )}
    >
      {/* Card label */}
      <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-[#64748b]">
        {card.label}
      </span>

      {/* Value row */}
      <div className="flex items-baseline gap-2 mt-0.5">
        <span
          className={cn(
            "text-2xl font-semibold font-mono leading-none tabular-nums tracking-tight",
            card.accent === "neutral" ? "text-[#e2e8f0]" : undefined
          )}
          style={
            card.accent !== "neutral"
              ? { color: ACCENT_COLOR[card.accent] }
              : undefined
          }
        >
          {card.value}
        </span>

        {/* Delta */}
        {card.delta && (
          <span
            className="text-xs font-mono tabular-nums font-medium"
            style={{
              color:
                card.delta.direction === "up"
                  ? "#22c55e"
                  : card.delta.direction === "down"
                    ? "#ef4444"
                    : "#64748b",
            }}
          >
            {card.delta.direction === "up" && "▲ "}
            {card.delta.direction === "down" && "▼ "}
            {card.delta.value}
          </span>
        )}
      </div>

      {/* Sparkline */}
      {card.sparkline && card.sparkline.length >= 2 && (
        <Sparkline
          data={card.sparkline}
          color={card.sparklineColor ?? ACCENT_COLOR[card.accent]}
          refValue={card.sparklineRef}
        />
      )}

      {/* Threshold bar */}
      {card.thresholdBar && (
        <div className="mt-auto pt-2">
          <div className="h-[3px] w-full bg-[#1e293b] overflow-hidden">
            <div
              className="h-full transition-all duration-500 ease-out"
              style={{
                width: `${Math.min(1, Math.max(0, card.thresholdBar.current / card.thresholdBar.max)) * 100}%`,
                backgroundColor: ACCENT_COLOR[card.accent],
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function StatsStrip({ groups, className }: StatsStripProps) {
  return (
    <div
      className={cn(
        "hidden md:flex w-full border border-border bg-[#080808] overflow-hidden",
        className
      )}
    >
      {groups.map((group, gi) => (
        <div key={group.label} className="flex flex-1 min-w-0">
          {/* Group separator */}
          {gi > 0 && (
            <div className="w-px bg-[#334155] self-stretch flex-shrink-0" />
          )}

          {/* Group content */}
          <div className="flex flex-1 min-w-0 flex-col">
            {/* Group label */}
            <div className="px-4 pt-2 pb-0">
              <span className="font-mono text-[8px] font-medium uppercase tracking-[0.12em] text-[#3a3a3a]">
                {group.label}
              </span>
            </div>

            {/* Cards row */}
            <div className="flex flex-1 min-w-0">
              {group.cards.map((card, ci) => (
                <KpiCardCell
                  key={card.label}
                  card={card}
                  showSeparator={ci < group.cards.length - 1}
                />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
