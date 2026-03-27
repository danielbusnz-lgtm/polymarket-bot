"use client"

import { useEffect, useRef, useState } from "react"
import {
  createChart,
  AreaSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type AreaData,
  type Time,
} from "lightweight-charts"
import { cn } from "@/lib/utils"

type Timeframe = "1D" | "1W" | "1M" | "ALL"

interface EquityCurveProps {
  data: { time: number; value: number }[]
  className?: string
}

const TIMEFRAMES: Timeframe[] = ["1D", "1W", "1M", "ALL"]

function filterByTimeframe(
  data: { time: number; value: number }[],
  tf: Timeframe
): { time: number; value: number }[] {
  if (tf === "ALL" || data.length === 0) return data
  const latest = data[data.length - 1].time
  const cutoffs: Record<string, number> = {
    "1D": latest - 86_400,
    "1W": latest - 7 * 86_400,
    "1M": latest - 30 * 86_400,
  }
  return data.filter((d) => d.time >= cutoffs[tf])
}

function formatUSD(n: number): string {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function EquityCurve({ data, className }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null)
  const [timeframe, setTimeframe] = useState<Timeframe>("ALL")
  const [hoverInfo, setHoverInfo] = useState<{
    value: number
    time: string
  } | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0a0a0a" },
        textColor: "#4b5563",
        fontFamily:
          'ui-monospace, "Cascadia Mono", "Segoe UI Mono", monospace',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(255, 255, 255, 0.25)",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1a1a1a",
        },
        horzLine: {
          color: "rgba(255, 255, 255, 0.25)",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1a1a1a",
        },
      },
      rightPriceScale: {
        borderColor: "#1f2937",
        scaleMargins: { top: 0.1, bottom: 0.05 },
      },
      timeScale: {
        borderColor: "#1f2937",
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: false,
      handleScale: false,
    })

    const series = chart.addSeries(AreaSeries, {
      lineColor: "#22c55e",
      topColor: "rgba(34, 197, 94, 0.25)",
      bottomColor: "rgba(34, 197, 94, 0.00)",
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: "#22c55e",
      crosshairMarkerBackgroundColor: "#0a0a0a",
      crosshairMarkerBorderWidth: 2,
    })

    chartRef.current = chart
    seriesRef.current = series

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData.has(series)) {
        setHoverInfo(null)
        return
      }
      const point = param.seriesData.get(series) as
        | AreaData<Time>
        | undefined
      if (point && "value" in point) {
        const date = new Date((param.time as number) * 1000)
        const timeStr = date.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
        setHoverInfo({ value: point.value, time: timeStr })
      }
    })

    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    const filtered = filterByTimeframe(data, timeframe)
    seriesRef.current.setData(
      filtered.map((d) => ({ time: d.time as Time, value: d.value }))
    )
    chartRef.current.timeScale().fitContent()
  }, [data, timeframe])

  const latestValue =
    data.length > 0 ? data[data.length - 1].value : null
  const displayValue = hoverInfo?.value ?? latestValue
  const displayTime = hoverInfo?.time ?? "Current"

  return (
    <div
      className={cn(
        "flex flex-col border border-border bg-[#0a0a0a]",
        className
      )}
    >
      <div className="flex items-center justify-between px-4 h-10 border-b border-border flex-shrink-0">
        <div className="flex items-baseline gap-3">
          <span className="font-mono font-bold text-[1.15rem] tabular-nums text-[#e8e8e8]">
            {displayValue != null ? formatUSD(displayValue) : "--"}
          </span>
          <span className="font-mono text-[0.65rem] text-[#555] uppercase tracking-wider">
            {displayTime}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                "px-2 py-0.5 text-[0.65rem] font-mono font-semibold uppercase tracking-wider border transition-colors",
                timeframe === tf
                  ? "text-emerald-500 border-emerald-500/40 bg-emerald-500/5"
                  : "text-[#555] border-transparent hover:text-[#999]"
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  )
}
