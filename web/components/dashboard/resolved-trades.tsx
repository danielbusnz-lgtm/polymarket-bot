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
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { ModelVoteStrip, type VoteData, type ModelVote } from "./model-vote-strip"
import { PositionStateStrip } from "./position-state-strip"

const MODEL_NAMES = ["Claude", "GPT-4o", "Gemini", "Grok-3", "DeepSeek"]

function seededRandom(seed: number) {
  return () => {
    seed = (seed * 16807 + 0) % 2147483647
    return seed / 2147483647
  }
}

function generateVotes(trade: Trade, index: number): VoteData {
  const rand = seededRandom(index * 31 + 7)
  const baseProb = trade.avg_prob
  const votes: ModelVote[] = MODEL_NAMES.map((model) => {
    const noise = (rand() - 0.5) * 0.20
    const prob = Math.min(0.98, Math.max(0.02, baseProb + noise))
    return { model, probability: prob, dropped: false }
  })

  // Mark min and max as dropped
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
    marketPrice: trade.price,
    edge: trade.edge,
    outcome: trade.correct,
  }
}

import type { Signal } from "@/lib/types"

type Trade = Signal

interface ResolvedTradesProps {
  trades: Trade[]
  className?: string
}

type Filter = "all" | "win" | "loss"
type SortCol = "date" | "edge" | "result"
type SortDir = "asc" | "desc"

function formatDate(iso: string): { text: string; opacity: string } {
  const date = new Date(iso)
  const now = Date.now()
  const diff = now - date.getTime()
  const hours = diff / (1000 * 60 * 60)
  const days = hours / 24

  let text: string
  if (hours < 24) {
    text = `${Math.floor(hours)}h ago`
  } else if (days < 7) {
    text = `${Math.floor(days)}d ago`
  } else {
    text = date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
  }

  const opacity =
    days < 7 ? "text-[#c8c8c8]" : days < 30 ? "text-[#999]" : "text-[#777]"

  return { text, opacity }
}

function pct(n: number, decimals = 1): string {
  return (n * 100).toFixed(decimals) + "%"
}

const HEAD = "h-9 px-3 font-mono text-[0.65rem] uppercase tracking-wider"

function SortHeader({
  label,
  column,
  currentSort,
  onSort,
  align = "left",
}: {
  label: string
  column: SortCol
  currentSort: { col: SortCol; dir: SortDir }
  onSort: (col: SortCol) => void
  align?: "left" | "right" | "center"
}) {
  const isActive = currentSort.col === column
  const Icon = isActive
    ? currentSort.dir === "asc"
      ? ChevronUp
      : ChevronDown
    : ChevronsUpDown

  return (
    <TableHead
      className={cn(
        HEAD,
        isActive ? "text-[#888]" : "text-[#444]",
        align === "right" && "text-right",
        align === "center" && "text-center"
      )}
    >
      <button
        onClick={() => onSort(column)}
        className="flex items-center gap-1 hover:text-[#666] transition-colors"
      >
        {label}
        <Icon className={cn("w-3 h-3", isActive ? "text-[#666]" : "text-[#2a2a2a]")} />
      </button>
    </TableHead>
  )
}

export function ResolvedTrades({ trades, className }: ResolvedTradesProps) {
  const [filter, setFilter] = useState<Filter>("all")
  const [sort, setSort] = useState<{ col: SortCol; dir: SortDir }>({
    col: "date",
    dir: "desc",
  })
  const [pageIndex, setPageIndex] = useState(0)
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const toggleRow = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }
  const [pageSize, setPageSize] = useState(25)

  const resolved = useMemo(
    () => trades.filter((t) => t.correct !== null),
    [trades]
  )

  const winCount = useMemo(
    () => resolved.filter((t) => t.correct === 1).length,
    [resolved]
  )
  const winRate =
    resolved.length > 0
      ? ((winCount / resolved.length) * 100).toFixed(1)
      : "0"

  const handleSort = (col: SortCol) => {
    if (sort.col === col) {
      setSort({ col, dir: sort.dir === "asc" ? "desc" : "asc" })
    } else {
      setSort({ col, dir: "desc" })
    }
    setPageIndex(0)
  }

  const handleFilter = (f: Filter) => {
    setFilter(f)
    setPageIndex(0)
  }

  const filtered = useMemo(() => {
    let data = resolved
    if (filter === "win") data = data.filter((t) => t.correct === 1)
    if (filter === "loss") data = data.filter((t) => t.correct === 0)

    data = [...data].sort((a, b) => {
      const dir = sort.dir === "asc" ? 1 : -1
      if (sort.col === "date")
        return dir * (new Date(a.run_at).getTime() - new Date(b.run_at).getTime())
      if (sort.col === "edge") return dir * (a.edge - b.edge)
      if (sort.col === "result") return dir * ((a.correct ?? 0) - (b.correct ?? 0))
      return 0
    })

    return data
  }, [resolved, filter, sort])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const page = filtered.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)

  return (
    <div className={cn("flex flex-col bg-[#0d0d0d] border border-[#242424]", className)}>
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 h-10 border-b border-[#1a1a1a]">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.7rem] text-[#888] uppercase tracking-[0.12em] font-medium">
            Resolved Trades
          </span>
          <span className="font-mono text-[0.6rem] text-[#555] tabular-nums">
            {filtered.length} trades
          </span>
          <span className="font-mono text-[0.6rem] text-[#555]">·</span>
          <span className="font-mono text-[0.6rem] text-emerald-800 tabular-nums">
            {winRate}% win rate
          </span>
        </div>
        <div className="flex items-center gap-0.5 border border-[#1f1f1f] rounded-sm p-0.5 bg-[#0a0a0a]">
          {(["all", "win", "loss"] as const).map((f) => (
            <button
              key={f}
              onClick={() => handleFilter(f)}
              className={cn(
                "h-5 px-2.5 font-mono text-[0.6rem] uppercase tracking-wider transition-colors duration-100",
                filter === f
                  ? "text-[#999] bg-white/[0.06] rounded-sm border border-[#333]"
                  : "text-[#444] hover:text-[#666] border border-transparent"
              )}
            >
              {f === "all" ? "All" : f === "win" ? "Wins" : "Losses"}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <Table>
        <TableHeader>
          <TableRow className="border-b border-[#1a1a1a] hover:bg-transparent">
            <SortHeader
              label="Date"
              column="date"
              currentSort={sort}
              onSort={handleSort}
            />
            <TableHead className={cn(HEAD, "text-[#555]")}>Market</TableHead>
            <TableHead className={cn(HEAD, "text-[#555] text-center")}>
              Dir
            </TableHead>
            <TableHead className={cn(HEAD, "text-[#555] text-right")}>
              Price
            </TableHead>
            <SortHeader
              label="Edge"
              column="edge"
              currentSort={sort}
              onSort={handleSort}
              align="right"
            />
            <TableHead className={cn(HEAD, "text-[#555] text-right")}>
              Avg Prob
            </TableHead>
            <SortHeader
              label="Result"
              column="result"
              currentSort={sort}
              onSort={handleSort}
              align="center"
            />
          </TableRow>
        </TableHeader>

        <TableBody>
          {page.map((trade, i) => {
            const date = formatDate(trade.run_at)
            const isWin = trade.correct === 1
            const globalIdx = pageIndex * pageSize + i
            const isExpanded = expandedRows.has(globalIdx)
            const voteData = generateVotes(trade, globalIdx)
            return (
              <React.Fragment key={`${trade.run_at}-${i}`}><TableRow
                onClick={() => toggleRow(globalIdx)}
                className={cn(
                  "h-8 border-b border-[#1a1a1a] hover:bg-white/[0.025] transition-colors cursor-pointer",
                  isExpanded && "bg-white/[0.015]"
                )}
              >
                <TableCell className={cn("px-3 py-0 font-mono tabular-nums text-xs", date.opacity)}>
                  <span title={new Date(trade.run_at).toLocaleString()}>
                    {date.text}
                  </span>
                </TableCell>

                <TableCell className="px-3 py-0 max-w-[240px]">
                  <span
                    className="block truncate text-xs text-[#c8c8c8]"
                    title={trade.question}
                  >
                    {trade.question}
                  </span>
                </TableCell>

                <TableCell className="px-3 py-0 text-center">
                  <span
                    className={cn(
                      "inline-block px-1.5 py-0.5 font-mono text-[0.6rem] font-bold border",
                      trade.direction === "YES"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-[#F23645]/10 text-[#F23645] border-[#F23645]/20"
                    )}
                  >
                    {trade.direction}
                  </span>
                </TableCell>

                <TableCell className="px-3 py-0 text-right font-mono tabular-nums text-xs text-[#e8e8e8]">
                  {trade.price.toFixed(2)}
                </TableCell>

                <TableCell
                  className={cn(
                    "px-3 py-0 text-right font-mono tabular-nums text-xs",
                    trade.edge >= 0.005
                      ? "text-emerald-400"
                      : trade.edge <= -0.005
                        ? "text-[#F23645]"
                        : "text-[#555]"
                  )}
                >
                  {(trade.edge >= 0 ? "+" : "") + pct(trade.edge)}
                </TableCell>

                <TableCell className="px-3 py-0 text-right font-mono tabular-nums text-xs text-[#e8e8e8]">
                  {pct(trade.avg_prob)}
                </TableCell>

                <TableCell className="px-3 py-0 text-center">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[0.6rem] font-bold border",
                      isWin
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-[#F23645]/10 text-[#F23645] border-[#F23645]/20"
                    )}
                  >
                    <span
                      className={cn(
                        "inline-block w-1 h-1 rounded-full",
                        isWin ? "bg-emerald-400" : "bg-[#F23645]"
                      )}
                    />
                    {isWin ? "WIN" : "LOSS"}
                  </span>
                </TableCell>
              </TableRow>
              {isExpanded && (
                <TableRow className="hover:bg-transparent border-b border-[#1a1a1a] bg-[#0a0a0a]">
                  <TableCell colSpan={7} className="p-0">
                    <div className="border-l-2 border-[#1e1e1e]">
                      <PositionStateStrip signal={trade} />
                      <ModelVoteStrip data={voteData} />
                    </div>
                  </TableCell>
                </TableRow>
              )}
              </React.Fragment>
            )
          })}

          {page.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={7} className="h-32 text-center">
                <div className="flex flex-col items-center justify-center gap-1.5">
                  <span className="font-mono text-[0.65rem] uppercase tracking-wider text-[#333]">
                    No {filter === "win" ? "winning" : filter === "loss" ? "losing" : ""} trades
                  </span>
                  <span className="font-mono text-[0.6rem] text-[#2a2a2a]">
                    Adjust filter to see results
                  </span>
                </div>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {/* Pagination footer */}
      <div className="flex items-center justify-between px-4 h-10 border-t border-[#1a1a1a]">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[0.6rem] text-[#444] uppercase tracking-wider">
            Rows
          </span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPageIndex(0)
            }}
            className="h-6 px-1.5 bg-transparent border border-[#242424] font-mono text-[0.6rem] text-[#555] hover:border-[#333] focus:outline-none focus:border-[#444] appearance-none cursor-pointer"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </div>

        <span className="font-mono text-[0.65rem] text-[#c8c8c8] tabular-nums uppercase tracking-wider">
          PAGE {pageIndex + 1} OF {totalPages}
        </span>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setPageIndex(Math.max(0, pageIndex - 1))}
            disabled={pageIndex === 0}
            className="h-6 px-2.5 border border-[#242424] bg-transparent font-mono text-[0.6rem] text-[#c8c8c8] uppercase tracking-wider hover:bg-white/[0.04] hover:border-[#333] hover:text-[#e8e8e8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-100"
          >
            Prev
          </button>
          <button
            onClick={() => setPageIndex(Math.min(totalPages - 1, pageIndex + 1))}
            disabled={pageIndex >= totalPages - 1}
            className="h-6 px-2.5 border border-[#242424] bg-transparent font-mono text-[0.6rem] text-[#c8c8c8] uppercase tracking-wider hover:bg-white/[0.04] hover:border-[#333] hover:text-[#e8e8e8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-100"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
