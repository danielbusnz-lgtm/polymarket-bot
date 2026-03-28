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
  isRunning: boolean
  isPaperMode: boolean
  onModeToggle: (paper: boolean) => void
}

export function TopBar({
  isRunning,
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

      {/* Right cluster: system state + controls */}
      <div className="flex items-center gap-4">

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
