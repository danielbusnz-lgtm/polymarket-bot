"use client"

import { cn } from "@/lib/utils"
import type { Signal } from "@/lib/types"

interface PositionStateStripProps {
  signal: Signal
}

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

function Cell({
  label,
  children,
  isLast,
  accentColor,
}: {
  label: string
  children: React.ReactNode
  isLast?: boolean
  accentColor?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col gap-[3px] px-4 py-2.5 min-w-0",
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

export function PositionStateStrip({ signal }: PositionStateStripProps) {
  const entryPrice = signal.price
  const fillPrice = signal.fill_price
  const isLive = !!signal.live
  const orderId = signal.order_id
  const edge = signal.edge
  const avgProb = signal.avg_prob

  const slippage =
    fillPrice !== null && fillPrice !== undefined
      ? fillPrice - entryPrice
      : null

  const signalAge = formatSignalAge(signal.run_at)

  return (
    <div className="flex w-full border-t border-[#181818] border-b border-b-[#151515] bg-[#080808]">
      <Cell label="Entry Px">
        <Primary>{entryPrice.toFixed(3)}</Primary>
        {fillPrice !== null && fillPrice !== undefined && (
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
        )}
      </Cell>

      <Cell label="Edge" accentColor={getEdgeColor(edge)}>
        <Primary color={getEdgeColor(edge)} large>
          {pct(edge, true)}
        </Primary>
        <Sub>
          model {pct(avgProb)} &middot; mkt {pct(entryPrice)}
        </Sub>
      </Cell>

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
            <span className="font-mono tabular-nums text-[0.5rem] text-[#3d3d3d]">
              #{orderId.length > 10 ? orderId.slice(-10) : orderId}
            </span>
          )}
        </div>
      </Cell>
    </div>
  )
}
