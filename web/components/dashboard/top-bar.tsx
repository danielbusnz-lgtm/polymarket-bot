"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

const NAV_LINKS = [
  { label: "DASHBOARD", href: "/" },
  { label: "ANALYTICS", href: "/analytics" },
]

interface TopBarProps {
  nav: number
  dailyPnL: number
  dailyPnLPct: number
  isRunning: boolean
  isPaperMode: boolean
  onModeToggle: (paper: boolean) => void
}

function formatUSD(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}

export function TopBar({
  nav,
  dailyPnL,
  dailyPnLPct,
  isRunning,
  isPaperMode,
  onModeToggle,
}: TopBarProps) {
  const pathname = usePathname()
  const pnlPositive = dailyPnL >= 0

  return (
    <header className="sticky top-0 z-50 flex h-14 items-center gap-6 border-b border-border bg-background/95 px-4 backdrop-blur-sm">
      <span className="font-mono text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        PM-BOT
      </span>

      <div className="h-4 w-px bg-border" aria-hidden="true" />

      <div className="flex flex-col justify-center">
        <span className="font-mono text-2xl font-semibold tabular-nums leading-none">
          {formatUSD(nav)}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Portfolio NAV
        </span>
      </div>

      <div
        className={cn(
          "flex items-baseline gap-1.5 font-mono tabular-nums",
          pnlPositive ? "text-[#22c55e]" : "text-[#F23645]"
        )}
        aria-label={`Daily P&L: ${pnlPositive ? "up" : "down"} ${formatUSD(Math.abs(dailyPnL))}`}
      >
        <span className="text-sm font-medium">
          {pnlPositive ? "+" : ""}
          {formatUSD(dailyPnL)}
        </span>
        <span className="text-xs">
          ({pnlPositive ? "+" : ""}
          {dailyPnLPct.toFixed(2)}%)
        </span>
      </div>

      <div className="h-4 w-px bg-border" aria-hidden="true" />

      <nav className="flex items-center gap-0.5">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "px-2.5 py-1 font-mono text-[0.65rem] uppercase tracking-widest transition-colors",
              pathname === link.href
                ? "text-[#e8e8e8] border-b border-[#e8e8e8]"
                : "text-[#555] hover:text-[#999]"
            )}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            isRunning ? "animate-pulse bg-emerald-500" : "bg-zinc-500"
          )}
          aria-hidden="true"
        />
        <span className="font-mono text-xs font-medium uppercase tracking-wider">
          {isRunning ? "RUNNING" : "STOPPED"}
        </span>
      </div>

      <div className="h-4 w-px bg-border" aria-hidden="true" />

      <div className="flex items-center gap-2" role="group" aria-label="Trading mode">
        <span
          className={cn(
            "font-mono text-xs uppercase tracking-wider",
            !isPaperMode ? "font-semibold text-amber-400" : "text-muted-foreground"
          )}
        >
          LIVE
        </span>
        <Switch
          checked={isPaperMode}
          onCheckedChange={onModeToggle}
          aria-label="Toggle between live and paper trading"
        />
        <span
          className={cn(
            "font-mono text-xs uppercase tracking-wider",
            isPaperMode ? "font-semibold text-sky-400" : "text-muted-foreground"
          )}
        >
          PAPER
        </span>
      </div>
    </header>
  )
}
