"use client"

import { cn } from "@/lib/utils"
import type { Signal } from "@/lib/types"
import { ModelVoteStrip, type VoteData } from "./model-vote-strip"

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatAge(runAt: string): string {
  const diffMs = Date.now() - new Date(runAt).getTime()
  const min = Math.floor(diffMs / 60_000)
  const hr = Math.floor(min / 60)
  const day = Math.floor(hr / 24)
  if (day > 0) return `${day}d ${hr % 24}h`
  if (hr > 0) return `${hr}h ${min % 60}m`
  return `${min}m`
}

function pct(n: number, showSign = false): string {
  const val = (n * 100).toFixed(1) + "%"
  return showSign && n >= 0 ? "+" + val : val
}

function getEdgeColor(edge: number): string {
  if (edge >= 0.05) return "#22c55e"
  if (edge >= 0.02) return "#b0b0b0"
  if (edge >= 0) return "#737373"
  return "#F23645"
}

/* ------------------------------------------------------------------ */
/*  Stat chip (for the top strip)                                       */
/* ------------------------------------------------------------------ */

function Chip({
  label,
  value,
  color,
  dim,
}: {
  label: string
  value: string
  color?: string
  dim?: boolean
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[#4a4a4a]">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-[0.7rem] font-semibold tabular-nums",
          dim ? "text-[#4a4a4a]" : "text-[#c8c8c8]"
        )}
        style={color ? { color } : undefined}
      >
        {value}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Left panel: analytical key-value pairs                              */
/* ------------------------------------------------------------------ */

function DataPair({
  label,
  value,
  color,
  sub,
}: {
  label: string
  value: string
  color?: string
  sub?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[0.55rem] uppercase tracking-[0.06em] text-[#4a4a4a]">
        {label}
      </span>
      <span
        className="font-mono text-[0.82rem] font-semibold tabular-nums leading-none text-[#d8d8d8]"
        style={color ? { color } : undefined}
      >
        {value}
      </span>
      {sub && (
        <span className="font-mono text-[0.55rem] tabular-nums text-[#3a3a3a]">
          {sub}
        </span>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Probability comparison bar                                          */
/* ------------------------------------------------------------------ */

function ProbBar({
  modelProb,
  marketProb,
  direction,
}: {
  modelProb: number
  marketProb: number
  direction: string
}) {
  const mktPct = Math.min(100, Math.max(0, marketProb * 100))
  const modelPct = Math.min(100, Math.max(0, modelProb * 100))
  const isYes = direction === "YES"
  const gapLeft = Math.min(mktPct, modelPct)
  const gapWidth = Math.abs(modelPct - mktPct)
  const accentColor = isYes ? "#22c55e" : "#F23645"

  return (
    <div className="flex flex-col gap-1 mt-1">
      <div className="relative h-[5px] w-full bg-[#1e293b] overflow-hidden">
        {/* Edge gap */}
        <div
          className="absolute top-0 h-full"
          style={{
            left: `${gapLeft}%`,
            width: `${gapWidth}%`,
            backgroundColor: isYes
              ? "rgba(34, 197, 94, 0.3)"
              : "rgba(242, 54, 69, 0.3)",
          }}
        />
        {/* Market tick */}
        <div
          className="absolute top-0 h-full w-[2px] bg-[#64748b]"
          style={{ left: `${mktPct}%` }}
        />
        {/* Model tick */}
        <div
          className="absolute top-0 h-full w-[2px]"
          style={{ left: `${modelPct}%`, backgroundColor: accentColor }}
        />
      </div>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1">
          <span className="inline-block w-1 h-1 bg-[#64748b]" />
          <span className="font-mono text-[0.5rem] text-[#525252] tabular-nums">
            mkt {mktPct.toFixed(0)}%
          </span>
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-1 h-1"
            style={{ backgroundColor: accentColor }}
          />
          <span
            className="font-mono text-[0.5rem] tabular-nums"
            style={{ color: accentColor }}
          >
            model {modelPct.toFixed(0)}%
          </span>
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main expanded detail                                                */
/* ------------------------------------------------------------------ */

interface PositionDetailProps {
  signal: Signal
  voteData: VoteData
  livePrice?: number | null
}

export function PositionDetail({ signal, voteData, livePrice }: PositionDetailProps) {
  const entryPrice = signal.price
  const fillPrice = signal.fill_price
  const isLive = !!signal.live
  const orderId = signal.order_id

  const slippage =
    fillPrice !== null && fillPrice !== undefined
      ? fillPrice - entryPrice
      : null

  const slippageText =
    slippage !== null && Math.abs(slippage) >= 0.001
      ? `${slippage >= 0 ? "+" : ""}${(slippage * 1000).toFixed(1)}m`
      : null

  const slippageColor =
    slippage !== null
      ? Math.abs(slippage) < 0.001
        ? "#525252"
        : slippage > 0
          ? "#F23645"
          : "#22c55e"
      : undefined

  // Live price movement
  const hasLive = livePrice != null
  const priceDelta = hasLive ? livePrice - entryPrice : 0
  const priceDeltaPct = hasLive && entryPrice > 0 ? (priceDelta / entryPrice) * 100 : 0
  const isWinning =
    hasLive &&
    ((signal.direction === "YES" && livePrice > entryPrice) ||
      (signal.direction === "NO" && livePrice < entryPrice))
  const movementColor = hasLive
    ? isWinning
      ? "#22c55e"
      : Math.abs(priceDelta) < 0.005
        ? "#525252"
        : "#F23645"
    : undefined

  return (
    <div className="border-l-2 border-[#1e1e1e] bg-[#070707]">
      {/* ---- Stat strip ---- */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-[#141414]">
        <Chip label="Entry" value={entryPrice.toFixed(3)} />

        {hasLive ? (
          <Chip label="Mark" value={livePrice.toFixed(3)} color={movementColor} />
        ) : (
          <Chip label="Mark" value={"\u2014"} dim />
        )}

        {hasLive ? (
          <Chip
            label="Move"
            value={`${priceDelta >= 0 ? "+" : ""}${priceDelta.toFixed(3)} (${priceDeltaPct >= 0 ? "+" : ""}${priceDeltaPct.toFixed(1)}%)`}
            color={movementColor}
          />
        ) : (
          <Chip label="Move" value={"\u2014"} dim />
        )}

        {/* Separator */}
        <div className="h-3 w-px bg-[#1e1e1e]" />

        {fillPrice !== null && fillPrice !== undefined ? (
          <Chip label="Fill" value={fillPrice.toFixed(3)} />
        ) : (
          <Chip label="Fill" value={"\u2014"} dim />
        )}

        {slippageText ? (
          <Chip label="Slip" value={slippageText} color={slippageColor} />
        ) : (
          <Chip label="Slip" value={"\u2014"} dim />
        )}

        {/* Separator */}
        <div className="h-3 w-px bg-[#1e1e1e]" />

        <Chip label="Age" value={formatAge(signal.run_at)} />

        <span
          className={cn(
            "inline-block px-1 py-px font-mono text-[0.5rem] font-bold leading-none border tracking-wide",
            isLive
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-amber-500/10 text-amber-400 border-amber-500/20"
          )}
        >
          {isLive ? "LIVE" : "PAPER"}
        </span>

        {orderId !== null && (
          <span
            className="font-mono tabular-nums text-[0.5rem] text-[#2a2a2a] cursor-help ml-auto"
            title={orderId}
          >
            #{orderId.length > 10 ? orderId.slice(-10) : orderId}
          </span>
        )}
      </div>

      {/* ---- Model vote visualization ---- */}
      <ModelVoteStrip data={voteData} />
    </div>
  )
}
