"use client"

import { EquityCurve } from "@/components/dashboard/equity-curve"
import { OpenPositions } from "@/components/dashboard/open-positions"
import { useSnapshots, useSignals } from "@/lib/hooks"

export default function DashboardPage() {
  const { data: snapshots } = useSnapshots("paper")
  const { data: openSignals } = useSignals("open")

  const chartData = (snapshots ?? []).map((s) => ({
    time: Math.floor(s.timestamp),
    value: s.value,
  }))

  return (
    <>
      <EquityCurve data={chartData} className="h-[420px]" />
      <OpenPositions signals={openSignals ?? []} />
    </>
  )
}
