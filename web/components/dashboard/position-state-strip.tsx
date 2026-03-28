"use client"

import { cn } from "@/lib/utils"
import type { Signal } from "@/lib/types"

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatSignalAge(runAt: string): string {
  const then = new Date(runAt).getTime()
  const diffMs = Date.now() - then
  const diffMin = Math.floor(diffMs / 60_000)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay > 0) return `${diffDay}d ${diffHr % 24}h`
  if (diffHr > 0) return `${diffHr}h ${diffMin % 60}m`
  return `${diffMin}m`
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

function getSlippageColor(slippage: number): string {
  if (Math.abs(slippage) < 0.001) return "#737373"
  return slippage > 0 ? "#F23645" : "#22c55e"
}

/* ------------------------------------------------------------------ */
/*  Primitives                                                          */
/* ------------------------------------------------------------------ */

function Cell({
  label,
  children,
  isLast,
  accentColor,
  wide,
}: {
  label: string
  children: React.ReactNode
  isLast?: boolean
  accentColor?: string
  wide?: boolean
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-[3px] px-4 py-2.5 min-w-0",
        wide ? "flex-[1.6]" : "flex-1",
        !isLast && "border-r border-[#1a1a1a]"
      )}
      style={accentColor ? { borderLeft: `2px solid ${accentColor}` } : undefined}
    >
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.06em] font-mono text-[#525252]">
        {label}
      </span>
      {children}
    </div>
  )
}

function Primary({
  children,
  color,
  dim,
  large,
}: {
  children: React.ReactNode
  color?: string
  dim?: boolean
  large?: boolean
}) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums leading-none mt-0.5",
        large ? "font-bold text-[0.94rem]" : "font-semibold text-[0.82rem]",
        dim ? "text-[#484848]" : "text-[#d8d8d8]"
      )}
      style={color ? { color } : undefined}
    >
      {children}
    </span>
  )
}

function Sub({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono tabular-nums text-[0.6rem] text-[#4a4a4a] leading-none mt-0.5">
      {children}
    </span>
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

  // The edge gap: region between market and model
  const gapLeft = Math.min(mktPct, modelPct)
  const gapWidth = Math.abs(modelPct - mktPct)
  const edgeColor = isYes ? "rgba(34, 197, 94, 0.35)" : "rgba(242, 54, 69, 0.35)"

  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {/* Bar */}
      <div className="relative h-[6px] w-full bg-[#1e293b] overflow-hidden">
        {/* Edge gap highlight */}
        <div
          className="absolute top-0 h-full"
          style={{
            left: `${gapLeft}%`,
            width: `${gapWidth}%`,
            backgroundColor: edgeColor,
          }}
        />

        {/* Market price tick */}
        <div
          className="absolute top-0 h-full w-[2px] bg-[#64748b]"
          style={{ left: `${mktPct}%` }}
        />

        {/* Model consensus tick */}
        <div
          className="absolute top-0 h-full w-[2px]"
          style={{
            left: `${modelPct}%`,
            backgroundColor: isYes ? "#22c55e" : "#F23645",
          }}
        />
      </div>

      {/* Labels below bar */}
      <div className="flex justify-between items-center">
        <span className="font-mono text-[0.5rem] text-[#4a4a4a] tabular-nums">0%</span>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="inline-block w-1.5 h-1.5 bg-[#64748b]" />
            <span className="font-mono text-[0.5rem] text-[#64748b] tabular-nums">
              mkt {mktPct.toFixed(0)}%
            </span>
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block w-1.5 h-1.5"
              style={{ backgroundColor: isYes ? "#22c55e" : "#F23645" }}
            />
            <span
              className="font-mono text-[0.5rem] tabular-nums"
              style={{ color: isYes ? "#22c55e" : "#F23645" }}
            >
              model {modelPct.toFixed(0)}%
            </span>
          </span>
        </div>
        <span className="font-mono text-[0.5rem] text-[#4a4a4a] tabular-nums">100%</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main component                                                      */
/* ------------------------------------------------------------------ */

export function PositionStateStrip({ signal }: { signal: Signal }) {
  const entryPrice = signal.price
  const fillPrice = signal.fill_price
  const isLive = !!signal.live
  const orderId = signal.order_id
  const edge = signal.edge
  const avgProb = signal.avg_prob
  const disagreement = signal.disagreement

  const slippage =
    fillPrice !== null && fillPrice !== undefined
      ? fillPrice - entryPrice
      : null

  const signalAge = formatSignalAge(signal.run_at)
  const highDisagreement = disagreement > 0.15

  return (
    <div className="flex w-full border-t border-[#181818] border-b border-b-[#151515] bg-[#080808]">
      {/* Entry price + fill */}
      <Cell label="Entry Px">
        <Primary>{entryPrice.toFixed(3)}</Primary>
        {fillPrice !== null && fillPrice !== undefined ? (
          <Sub>
            fill{" "}
            <span className="text-[#787878]">{fillPrice.toFixed(3)}</span>
            {slippage !== null && Math.abs(slippage) >= 0.001 && (
              <span style={{ color: getSlippageColor(slippage) }}>
                {" "}
                {slippage >= 0 ? "+" : ""}
                {(slippage * 1000).toFixed(1)}m slip
              </span>
            )}
          </Sub>
        ) : (
          <Sub>
            <span className="text-[#3a3a3a]">no fill (paper)</span>
          </Sub>
        )}
      </Cell>

      {/* Edge with accent bar */}
      <Cell label="Edge" accentColor={getEdgeColor(edge)}>
        <Primary color={getEdgeColor(edge)} large>
          {pct(edge, true)}
        </Primary>
        <Sub>
          model {pct(avgProb)} · mkt {pct(entryPrice)}
        </Sub>
      </Cell>

      {/* Probability comparison bar */}
      <Cell label="Model vs Market" wide>
        <ProbBar
          modelProb={avgProb}
          marketProb={entryPrice}
          direction={signal.direction}
        />
      </Cell>

      {/* Disagreement */}
      <Cell label="Disagreement">
        <Primary
          color={highDisagreement ? "#F23645" : "#737373"}
        >
          {pct(disagreement, false)}
        </Primary>
        <Sub>
          {highDisagreement ? (
            <span className="text-[#F23645]">high variance</span>
          ) : (
            <span className="text-[#3a3a3a]">models aligned</span>
          )}
        </Sub>
      </Cell>

      {/* Age + status */}
      <Cell label="Age" isLast>
        <Primary dim={!isLive}>{signalAge}</Primary>
        <div className="flex items-center gap-1.5 mt-0.5">
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
              className="font-mono tabular-nums text-[0.5rem] text-[#3d3d3d] cursor-help"
              title={orderId}
            >
              #{orderId.length > 8 ? orderId.slice(-8) : orderId}
            </span>
          )}
        </div>
      </Cell>
    </div>
  )
}
