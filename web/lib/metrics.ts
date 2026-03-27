import type { PortfolioSnapshot, Stats } from "./types"

export interface DerivedMetrics {
  maxDrawdown: number
  maxDrawdownPct: number
  sharpeRatio: number | null
  profitFactor: number | null
  winRateSeries: number[]
}

/**
 * Compute max drawdown from a snapshot series.
 * Returns the largest peak-to-trough decline as both absolute and percentage.
 */
function computeMaxDrawdown(snapshots: PortfolioSnapshot[]): {
  maxDrawdown: number
  maxDrawdownPct: number
} {
  if (snapshots.length < 2) return { maxDrawdown: 0, maxDrawdownPct: 0 }

  let peak = snapshots[0].value
  let maxDd = 0
  let maxDdPct = 0

  for (const snap of snapshots) {
    if (snap.value > peak) peak = snap.value
    const dd = peak - snap.value
    const ddPct = peak > 0 ? dd / peak : 0
    if (dd > maxDd) {
      maxDd = dd
      maxDdPct = ddPct
    }
  }

  return { maxDrawdown: maxDd, maxDrawdownPct: maxDdPct }
}

/**
 * Compute annualized Sharpe ratio from snapshot series.
 * Uses simple period returns, assumes risk-free rate of 0.
 */
function computeSharpe(snapshots: PortfolioSnapshot[]): number | null {
  if (snapshots.length < 3) return null

  const returns: number[] = []
  for (let i = 1; i < snapshots.length; i++) {
    const prev = snapshots[i - 1].value
    if (prev > 0) {
      returns.push((snapshots[i].value - prev) / prev)
    }
  }

  if (returns.length < 2) return null

  const mean = returns.reduce((a, b) => a + b, 0) / returns.length
  const variance =
    returns.reduce((sum, r) => sum + (r - mean) ** 2, 0) / (returns.length - 1)
  const std = Math.sqrt(variance)

  if (std === 0) return null

  // Estimate periods per year from average interval
  const totalSec =
    snapshots[snapshots.length - 1].timestamp - snapshots[0].timestamp
  const avgInterval = totalSec / (snapshots.length - 1)
  const periodsPerYear = avgInterval > 0 ? (365.25 * 86_400) / avgInterval : 252

  return (mean / std) * Math.sqrt(periodsPerYear)
}

/**
 * Compute profit factor from stats.
 * Uses wins * avg_edge as gross profit proxy and losses * avg_edge as gross loss proxy.
 * This is approximate since we don't have per-trade P&L amounts.
 */
function computeProfitFactor(stats: Stats): number | null {
  if (stats.losses === 0 && stats.wins === 0) return null
  if (stats.losses === 0) return stats.wins > 0 ? Infinity : null
  if (stats.wins === 0) return 0

  // Simple ratio: wins / losses weighted by win rate
  // With only count data, profit factor approximation is wins/losses
  // This gives a directional sense; real P&L would be better
  const winRate = stats.win_rate ?? 0
  const lossRate = 1 - winRate
  if (lossRate === 0) return null

  return winRate > 0 ? winRate / lossRate : 0
}

/**
 * Compute a rolling win rate series from resolved signals.
 * Returns the last `windowSize` rolling win rate values for sparkline use.
 */
function computeWinRateSeries(
  resolvedSignals: { correct: number | null }[],
  windowSize = 10,
  maxPoints = 20
): number[] {
  const resolved = resolvedSignals.filter((s) => s.correct !== null)
  if (resolved.length < windowSize) return []

  const series: number[] = []
  for (let i = windowSize; i <= resolved.length; i++) {
    const window = resolved.slice(i - windowSize, i)
    const wins = window.filter((s) => s.correct === 1).length
    series.push(wins / windowSize)
  }

  // Return only the most recent points for the sparkline
  return series.slice(-maxPoints)
}

export function computeDerivedMetrics(
  snapshots: PortfolioSnapshot[],
  stats: Stats,
  resolvedSignals: { correct: number | null }[]
): DerivedMetrics {
  const { maxDrawdown, maxDrawdownPct } = computeMaxDrawdown(snapshots)
  const sharpeRatio = computeSharpe(snapshots)
  const profitFactor = computeProfitFactor(stats)
  const winRateSeries = computeWinRateSeries(resolvedSignals)

  return {
    maxDrawdown,
    maxDrawdownPct,
    sharpeRatio,
    profitFactor,
    winRateSeries,
  }
}
