"use client"

import { useEffect, useRef, useState, useMemo } from "react"
import {
  createChart,
  BaselineSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type SingleValueData,
  type Time,
  type IPriceLine,
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

function getPeriodReturn(
  data: { time: number; value: number }[],
  tf: Timeframe
): number | null {
  const filtered = filterByTimeframe(data, tf)
  if (filtered.length < 2) return null
  const start = filtered[0].value
  const end = filtered[filtered.length - 1].value
  return ((end - start) / start) * 100
}

export function EquityCurve({ data, className }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<"Baseline"> | null>(null)
  const hwmLineRef = useRef<IPriceLine | null>(null)
  const [timeframe, setTimeframe] = useState<Timeframe>("ALL")
  const [hoverInfo, setHoverInfo] = useState<{
    value: number
    time: string
  } | null>(null)

  // Period returns for button labels
  const periodReturns = useMemo(() => {
    const returns: Record<Timeframe, number | null> = {
      "1D": getPeriodReturn(data, "1D"),
      "1W": getPeriodReturn(data, "1W"),
      "1M": getPeriodReturn(data, "1M"),
      ALL: getPeriodReturn(data, "ALL"),
    }
    return returns
  }, [data])

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
        horzLines: { color: "rgba(255, 255, 255, 0.06)" },
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

    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: 0 },
      topLineColor: "#22c55e",
      topFillColor1: "rgba(34, 197, 94, 0.20)",
      topFillColor2: "rgba(34, 197, 94, 0.02)",
      bottomLineColor: "#F23645",
      bottomFillColor1: "rgba(242, 54, 69, 0.02)",
      bottomFillColor2: "rgba(242, 54, 69, 0.20)",
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
    })

    chartRef.current = chart
    seriesRef.current = series

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData.has(series)) {
        setHoverInfo(null)
        return
      }
      const point = param.seriesData.get(series) as
        | SingleValueData<Time>
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
      hwmLineRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    const filtered = filterByTimeframe(data, timeframe)
    if (filtered.length === 0) return

    const baseValue = filtered[0].value

    seriesRef.current.setData(
      filtered.map((d) => ({ time: d.time as Time, value: d.value }))
    )
    seriesRef.current.applyOptions({
      baseValue: { type: "price", price: baseValue },
    })

    // High watermark line
    if (hwmLineRef.current) {
      seriesRef.current.removePriceLine(hwmLineRef.current)
      hwmLineRef.current = null
    }
    const hwm = Math.max(...data.map((d) => d.value))
    hwmLineRef.current = seriesRef.current.createPriceLine({
      price: hwm,
      color: "rgba(251, 191, 36, 0.4)",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "HWM",
      axisLabelColor: "rgba(251, 191, 36, 0.6)",
      axisLabelTextColor: "#0a0a0a",
    })

    chartRef.current.timeScale().fitContent()
  }, [data, timeframe])

  const filtered = filterByTimeframe(data, timeframe)
  const latestValue = data.length > 0 ? data[data.length - 1].value : null
  const startValue = filtered.length > 0 ? filtered[0].value : null
  const displayValue = hoverInfo?.value ?? latestValue
  const displayTime = hoverInfo?.time ?? "Current"

  const hwm = data.length > 0 ? Math.max(...data.map((d) => d.value)) : null
  const currentDD =
    latestValue != null && hwm != null && hwm > 0
      ? ((latestValue - hwm) / hwm) * 100
      : 0

  const pctChange =
    displayValue != null && startValue != null && startValue > 0
      ? ((displayValue - startValue) / startValue) * 100
      : null
  const pctPositive = pctChange != null && pctChange >= 0

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
          {pctChange != null && (
            <span
              className={cn(
                "font-mono text-[0.8rem] font-semibold tabular-nums",
                pctPositive ? "text-[#22c55e]" : "text-[#F23645]"
              )}
            >
              {pctPositive ? "+" : ""}
              {pctChange.toFixed(2)}%
            </span>
          )}
          <span className="font-mono text-[0.6rem] text-[#555] uppercase tracking-wider">
            {displayTime}
          </span>
          {currentDD < -0.5 && (
            <span className="font-mono text-[0.6rem] text-amber-500/80 tabular-nums">
              DD {currentDD.toFixed(1)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map((tf) => {
            const ret = periodReturns[tf]
            return (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  "px-2 py-0.5 text-[0.65rem] font-mono font-semibold uppercase tracking-wider border transition-colors",
                  timeframe === tf
                    ? "text-[#e8e8e8] border-[#e8e8e8]/20 bg-white/[0.04]"
                    : "text-[#555] border-transparent hover:text-[#999]"
                )}
              >
                {tf}
                {ret != null && (
                  <span
                    className={cn(
                      "ml-1 text-[0.55rem]",
                      ret >= 0 ? "text-[#22c55e]" : "text-[#F23645]"
                    )}
                  >
                    {ret >= 0 ? "+" : ""}
                    {ret.toFixed(1)}%
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  )
}
