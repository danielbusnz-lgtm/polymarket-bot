import { cn } from "@/lib/utils"

interface SectionHeaderProps {
  label: string
  className?: string
}

export function SectionHeader({ label, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex items-center gap-3 mb-2", className)}>
      <span className="font-mono text-[0.6rem] text-[#777] uppercase tracking-[0.15em]">
        {label}
      </span>
      <div className="flex-1 h-px bg-[#1a1a1a]" />
    </div>
  )
}
