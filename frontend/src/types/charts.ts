export type Threshold = { label: string; kind: 'upper' | 'lower'; value: number }

export type MetricInfo = {
  metric: string
  unit: string
  thresholds: Threshold[]
}

export type MetricsResp = { metrics: MetricInfo[] }

export type TimeseriesResp = {
  title: string
  unit: string
  labels: string[]
  series: { name: string; data: number[] }[]
  thresholds: Threshold[]
}

export type ScatterPoint = { ts: string; x: number; y: number }

export type ScatterResp = {
  title: string
  unit_x: string
  unit_y: string
  points: ScatterPoint[]
  best_fit: { slope: number; intercept: number } | null
  x_thresholds: Threshold[]
  y_thresholds: Threshold[]
}

export type RiskHeatmapRow = {
  metric: string
  unit: string
  thresholds: Threshold[]
  values: (number | null)[]
  risk: (number | null)[]
  enabled: boolean
  has_sensor: boolean
}

export type RiskHeatmapResp = {
  title: string
  start: string | null
  end: string | null
  interval: string
  labels: string[]
  rows: RiskHeatmapRow[]
}
