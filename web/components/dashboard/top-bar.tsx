"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { useCron } from "@/lib/hooks"

const NAV_LINKS = [
  { label: "DASHBOARD", href: "/" },
  { label: "ANALYTICS", href: "/analytics" },
]

interface TopBarProps {
  isPaperMode: boolean
  onModeToggle: (paper: boolean) => void
}

function CronCountdown() {
  const { data } = useCron()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])

  if (!data?.last_run) {
    return (
      <span className="font-mono text-[10px] text-white/20 uppercase tracking-[0.1em]">
        No runs yet
      </span>
    )
  }

  const lastRunDate = new Date(data.last_run * 1000)
  const elapsed = Math.floor((now / 1000) - data.last_run)
  const sixHours = 6 * 3600
  const remaining = Math.max(0, sixHours - elapsed)

  const hours = Math.floor(remaining / 3600)
  const minutes = Math.floor((remaining % 3600) / 60)
  const seconds = remaining % 60

  const isOverdue = remaining === 0
  const isSoon = remaining < 1800 && remaining > 0

  // Format last run as relative time
  const elapsedMin = Math.floor(elapsed / 60)
  const elapsedHr = Math.floor(elapsedMin / 60)
  const lastRunStr = elapsedHr > 0
    ? `${elapsedHr}h ${elapsedMin % 60}m ago`
    : `${elapsedMin}m ago`

  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          isOverdue
            ? "bg-amber-500/80 animate-pulse"
            : isSoon
              ? "bg-amber-500/60"
              : "bg-emerald-500/50"
        )}
      />
      <span
        className={cn(
          "font-mono text-[10px] tabular-nums uppercase tracking-[0.1em]",
          isOverdue ? "text-amber-500/70" : "text-white/35"
        )}
      >
        {isOverdue
          ? "OVERDUE"
          : `${hours}h ${minutes.toString().padStart(2, "0")}m ${seconds.toString().padStart(2, "0")}s`}
      </span>
      <span className="font-mono text-[9px] text-white/15">
        last {lastRunStr}
      </span>
    </div>
  )
}

export function TopBar({
  isPaperMode,
  onModeToggle,
}: TopBarProps) {
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-50 flex h-11 items-center border-b border-white/[0.06] bg-[#0a0a0a] px-4 backdrop-blur-sm">
      {/* Left cluster: brand + nav */}
      <div className="flex items-center gap-5">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.25em] text-white/60">
          SIGNUM
        </span>
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "px-2 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors",
                pathname === link.href
                  ? "text-white/80 border-b-2 border-[#4f8ef7]"
                  : "text-white/35 hover:text-white/60"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex-1" />

      {/* Right cluster: cron countdown + mode toggle */}
      <div className="flex items-center gap-4">
        <CronCountdown />

        <div className="h-3 w-px bg-white/10" aria-hidden="true" />

        <div className="flex items-center gap-1.5" role="group" aria-label="Trading mode">
          <span
            className={cn(
              "font-mono text-[10px] uppercase tracking-[0.1em]",
              !isPaperMode ? "text-white/80 font-semibold" : "text-white/20"
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
              "font-mono text-[10px] uppercase tracking-[0.1em]",
              isPaperMode ? "text-white/80 font-semibold" : "text-white/20"
            )}
          >
            PAPER
          </span>
        </div>
      </div>
    </header>
  )
}
