export interface PortfolioSnapshot {
  timestamp: number
  value: number
}

export interface Position {
  title: string
  direction: "YES" | "NO"
  amount_in: number
  current_value: number
  our_prob: number
  market_prob: number
  opened_at: number
}

export interface Signal {
  id: number
  run_at: string
  market_id: string
  question: string
  direction: string
  token_id: string
  price: number
  edge: number
  avg_prob: number
  disagreement: number
  live: number
  order_id: string | null
  fill_price: number | null
  resolved: number
  outcome: string | null
  correct: number | null
}

export interface EdgeBucket {
  label: string
  count: number
  win_rate: number
}

export interface Stats {
  total: number
  open: number
  live: number
  resolved: number
  wins: number
  losses: number
  win_rate: number | null
  avg_edge: number
  edge_buckets: EdgeBucket[]
}

export interface CronInfo {
  last_run: number | null
  seconds_until_next: number | null
}
