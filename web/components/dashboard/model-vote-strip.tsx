"use client"

import { cn } from "@/lib/utils"

export interface ModelVote {
  model: string
  probability: number
  dropped: boolean
}

export interface VoteData {
  votes: ModelVote[]
  consensus: number
  marketPrice: number
  edge: number
  outcome?: number | null
}

const MODEL_COLORS: Record<string, string> = {
  Claude: "#d97757",
  "GPT-4o": "#10a37f",
  Gemini: "#4796e3",
  "Grok-3": "#ffffff",
  DeepSeek: "#4d6bfe",
}

function pct(n: number): string {
  return (n * 100).toFixed(1) + "%"
}

export function ModelVoteStrip({ data }: { data: VoteData }) {
  const sorted = [...data.votes].sort((a, b) => b.probability - a.probability)

  const closestModel =
    data.outcome !== null && data.outcome !== undefined
      ? data.votes.reduce((best, v) => {
          const target = data.outcome as number
          return Math.abs(v.probability - target) < Math.abs(best.probability - target)
            ? v
            : best
        })
      : null

  return (
    <div className="px-4 py-3 flex gap-6">
      {/* Model rows with inline bars */}
      <div className="relative flex-1 min-w-0 flex flex-col">
        {sorted.map((v) => {
          const color = MODEL_COLORS[v.model] || "#555"
          const isClosest =
            data.outcome !== null &&
            data.outcome !== undefined &&
            closestModel?.model === v.model
          const barWidth = Math.max(1, v.probability * 100)

          return (
            <div
              key={v.model}
              className="flex items-center gap-3 py-2.5 group"
            >
              {/* Dot + Name */}
              <div className="flex w-28 items-center gap-1.5 min-w-0 flex-shrink-0">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{
                    backgroundColor: v.dropped ? "transparent" : color,
                    border: v.dropped ? `2px solid ${color}4d` : "none",
                  }}
                />
                <span
                  className={cn(
                    "truncate text-xs font-medium",
                    v.dropped ? "text-zinc-600" : "text-zinc-300"
                  )}
                >
                  {v.model}
                </span>
                {v.dropped && (
                  <span className="ml-0.5 shrink-0 text-[9px] uppercase tracking-wide text-zinc-600">
                    excl
                  </span>
                )}
              </div>

              {/* Bar track */}
              <div className="relative flex-1 min-w-0">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${barWidth}%`,
                      background: v.dropped
                        ? `${color}26`
                        : `linear-gradient(to bottom, ${color}cc, ${color}99)`,
                    }}
                  />
                </div>
              </div>

              {/* Value */}
              <span
                className={cn(
                  "w-12 text-right tabular-nums flex-shrink-0",
                  v.dropped
                    ? "text-xs font-medium text-zinc-600"
                    : "text-sm font-semibold text-zinc-100"
                )}
              >
                {pct(v.probability)}
              </span>
            </div>
          )
        })}

        {/* X axis */}
        <div className="flex items-center gap-3 pt-1">
          <div className="w-28 flex-shrink-0" />
          <div className="relative flex-1 min-w-0 flex justify-between">
            {[0, 25, 50, 75, 100].map((v) => (
              <span
                key={v}
                className="font-mono text-[8px] text-[#333] tabular-nums"
              >
                {v}%
              </span>
            ))}
          </div>
          <div className="w-12 flex-shrink-0" />
        </div>
      </div>

      {/* Summary stats */}
      <div className="flex flex-col justify-center gap-1.5 w-[140px] flex-shrink-0 border-l border-[#1a1a1a] pl-4">
        <div className="flex justify-between font-mono text-[0.65rem]">
          <span className="text-[#555]">Consensus</span>
          <span className="text-zinc-100 tabular-nums font-semibold">{pct(data.consensus)}</span>
        </div>
        <div className="flex justify-between font-mono text-[0.65rem]">
          <span className="text-[#555]">Market</span>
          <span className="text-[#4a9eff] tabular-nums">{pct(data.marketPrice)}</span>
        </div>
        <div className="flex justify-between font-mono text-[0.65rem]">
          <span className="text-[#555]">Edge</span>
          <span
            className={cn(
              "tabular-nums",
              data.edge >= 0 ? "text-emerald-400" : "text-[#F23645]"
            )}
          >
            {data.edge >= 0 ? "+" : ""}
            {pct(data.edge)}
          </span>
        </div>
        <div className="flex justify-between font-mono text-[0.65rem]">
          <span className="text-[#555]">Spread</span>
          <span className="text-zinc-300 tabular-nums">
            {pct(
              Math.max(...data.votes.map((v) => v.probability)) -
                Math.min(...data.votes.map((v) => v.probability))
            )}
          </span>
        </div>
        {data.outcome !== null && data.outcome !== undefined && (
          <div className="flex justify-between font-mono text-[0.65rem] border-t border-[#1a1a1a] pt-1.5">
            <span className="text-[#555]">Outcome</span>
            <span
              className={cn(
                "font-bold",
                data.outcome === 1 ? "text-emerald-400" : "text-[#F23645]"
              )}
            >
              {data.outcome === 1 ? "YES" : "NO"}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
