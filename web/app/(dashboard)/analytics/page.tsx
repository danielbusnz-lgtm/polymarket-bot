"use client"

import { useMemo } from "react"
import { SectionHeader } from "@/components/dashboard/section-header"
import { CalibrationChart } from "@/components/dashboard/calibration-chart"
import { EdgeHistogram } from "@/components/dashboard/edge-histogram"
import { EdgeOutcomeChart } from "@/components/dashboard/edge-outcome-chart"
import { RollingWinRate } from "@/components/dashboard/rolling-win-rate"
import { DisagreementAccuracyChart } from "@/components/dashboard/disagreement-accuracy-chart"
import { ResolvedTrades } from "@/components/dashboard/resolved-trades"
import { useSignals } from "@/lib/hooks"

function computeCalibrationData(
  trades: { avg_prob: number; correct: number | null }[]
) {
  const resolved = trades.filter((t) => t.correct !== null)
  const buckets = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
  return buckets
    .map((center) => {
      const lo = center - 0.05
      const hi = center + 0.05
      const inBucket = resolved.filter(
        (t) => t.avg_prob >= lo && t.avg_prob < hi
      )
      const count = inBucket.length
      const wins = inBucket.filter((t) => t.correct === 1).length
      const actual = count > 0 ? wins / count : center
      return { x: center, y: actual, count }
    })
    .filter((b) => b.count > 0)
}

export default function AnalyticsPage() {
  const { data: allSignals, isPending } = useSignals("all")

  const resolvedTrades = useMemo(
    () => (allSignals ?? []).filter((s) => s.correct !== null),
    [allSignals]
  )

  const calibrationData = useMemo(
    () => computeCalibrationData(resolvedTrades),
    [resolvedTrades]
  )

  if (isPending) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="font-mono text-[0.7rem] text-[#555] uppercase tracking-[0.12em]">
          Loading analytics...
        </span>
      </div>
    )
  }

  return (
    <>
      {/* Section 1: Model Health */}
      <section>
        <SectionHeader label="Model Health" />
        <RollingWinRate trades={resolvedTrades} className="h-[300px]" />
      </section>

      {/* Section 2: Signal Quality */}
      <section className="mt-6">
        <SectionHeader label="Signal Quality" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <CalibrationChart data={calibrationData} className="h-[380px]" />
          <EdgeOutcomeChart trades={resolvedTrades} className="h-[380px]" />
        </div>
      </section>

      {/* Section 3: Signal Distribution */}
      <section className="mt-6">
        <SectionHeader label="Signal Distribution" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <EdgeHistogram trades={allSignals ?? []} className="h-[360px]" />
          <DisagreementAccuracyChart
            trades={resolvedTrades}
            className="h-[360px]"
          />
        </div>
      </section>

      {/* Section 4: Resolved Trades */}
      <section className="mt-6">
        <SectionHeader label="Resolved Trades" />
        <ResolvedTrades trades={resolvedTrades} />
      </section>
    </>
  )
}
