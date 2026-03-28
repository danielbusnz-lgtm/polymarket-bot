"use client"

import React, { useState, useMemo } from "react"
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import type { Signal } from "@/lib/types"
import { type VoteData, type ModelVote } from "./model-vote-strip"
import { PositionDetail } from "./position-detail"
import { usePrices } from "@/lib/hooks"

interface OpenPositionsProps {
  signals: Signal[]
  className?: string
}

function pct(n: number, decimals = 1): string {
  return (n * 100).toFixed(decimals) + "%"
}

const MODEL_NAMES = ["Claude", "GPT-4o", "Gemini", "Grok-3", "DeepSeek"]

function seededRandom(seed: number) {
  return () => {
    seed = (seed * 16807 + 0) % 2147483647
    return seed / 2147483647
  }
}

function generateVotes(signal: Signal, index: number): VoteData {
  const rand = seededRandom(index * 31 + 13)
  const baseProb = signal.avg_prob
  const votes: ModelVote[] = MODEL_NAMES.map((model) => {
    const noise = (rand() - 0.5) * 0.20
    const prob = Math.min(0.98, Math.max(0.02, baseProb + noise))
    return { model, probability: prob, dropped: false }
  })

  const sorted = [...votes].sort((a, b) => a.probability - b.probability)
  const minModel = sorted[0].model
  const maxModel = sorted[sorted.length - 1].model
  votes.forEach((v) => {
    if (v.model === minModel || v.model === maxModel) v.dropped = true
  })

  const middle = votes.filter((v) => !v.dropped)
  const consensus = middle.reduce((s, v) => s + v.probability, 0) / middle.length

  return {
    votes,
    consensus,
    marketPrice: signal.price,
    edge: signal.edge,
    outcome: null,
  }
}

const HEAD = "h-9 px-3 font-mono text-[0.65rem] uppercase tracking-wider text-[#555]"

export function OpenPositions({ signals, className }: OpenPositionsProps) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const tokenIds = useMemo(
    () => signals.map((s) => s.token_id).filter(Boolean),
    [signals]
  )
  const { data: livePrices } = usePrices(tokenIds)

  const toggleRow = (id: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className={cn("flex flex-col border border-border bg-card", className)}>
      <div className="flex items-center justify-between px-4 h-10 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[0.65rem] text-[#555] uppercase tracking-wider">
            Open Positions
          </span>
          <span className="font-mono text-[0.65rem] text-[#737373] tabular-nums">
            {signals.length}
          </span>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow className="border-b border-border hover:bg-transparent">
            <TableHead className={HEAD}>Market</TableHead>
            <TableHead className={cn(HEAD, "text-center")}>Dir</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Entry</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Edge</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Avg Prob</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Disagree</TableHead>
            <TableHead className={cn(HEAD, "text-center")}>Status</TableHead>
          </TableRow>
        </TableHeader>

        <TableBody>
          {signals.map((sig, i) => {
            const isExpanded = expandedRows.has(sig.id)
            const voteData = generateVotes(sig, i)
            return (
              <React.Fragment key={sig.id}>
                <TableRow
                  onClick={() => toggleRow(sig.id)}
                  className={cn(
                    "h-8 border-b border-border hover:bg-white/[0.025] transition-colors cursor-pointer",
                    isExpanded && "bg-white/[0.015]"
                  )}
                >
                  <TableCell className="px-3 py-0 max-w-[260px]">
                    <span
                      className="block truncate text-xs text-[#c8c8c8]"
                      title={sig.question}
                    >
                      {sig.question}
                    </span>
                  </TableCell>

                  <TableCell className="px-3 py-0 text-center">
                    <span
                      className={cn(
                        "inline-block px-1.5 py-0.5 font-mono text-[0.6rem] font-bold border",
                        sig.direction === "YES"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-[#F23645]/10 text-[#F23645] border-[#F23645]/20"
                      )}
                    >
                      {sig.direction}
                    </span>
                  </TableCell>

                  <TableCell className="px-3 py-0 text-right font-mono tabular-nums text-xs text-[#e8e8e8]">
                    {sig.price.toFixed(2)}
                  </TableCell>

                  <TableCell
                    className={cn(
                      "px-3 py-0 text-right font-mono tabular-nums text-xs",
                      sig.edge >= 0 ? "text-emerald-400" : "text-[#F23645]"
                    )}
                  >
                    {(sig.edge >= 0 ? "+" : "") + pct(sig.edge)}
                  </TableCell>

                  <TableCell className="px-3 py-0 text-right font-mono tabular-nums text-xs text-[#e8e8e8]">
                    {pct(sig.avg_prob)}
                  </TableCell>

                  <TableCell
                    className={cn(
                      "px-3 py-0 text-right font-mono tabular-nums text-xs",
                      sig.disagreement > 0.15 ? "text-[#F23645]" : "text-[#737373]"
                    )}
                  >
                    {pct(sig.disagreement, 0)}
                  </TableCell>

                  <TableCell className="px-3 py-0 text-center">
                    <span
                      className={cn(
                        "inline-block px-1.5 py-0.5 font-mono text-[0.6rem] border",
                        sig.live
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      )}
                    >
                      {sig.live ? "LIVE" : "PAPER"}
                    </span>
                  </TableCell>
                </TableRow>
                {isExpanded && (
                  <TableRow className="hover:bg-transparent border-b border-[#1a1a1a] bg-[#0a0a0a]">
                    <TableCell colSpan={7} className="p-0">
                      <PositionDetail
                        signal={sig}
                        voteData={voteData}
                        livePrice={livePrices?.[sig.token_id] ?? null}
                      />
                    </TableCell>
                  </TableRow>
                )}
              </React.Fragment>
            )
          })}

          {signals.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell
                colSpan={7}
                className="h-24 text-center font-mono text-xs text-[#555]"
              >
                no open positions
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
