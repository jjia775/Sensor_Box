import type { RiskHeatmapResp, ScatterResp, TimeseriesResp } from './charts'

type BaseSection = {
  imageDataUrl: string
}

export type TimeseriesSection = BaseSection & {
  kind: 'timeseries'
  title: string
  filters: {
    serial: string
    metric: string
    interval: string
    aggregate: string
    range: string
  }
  data: TimeseriesResp
}

export type ScatterSection = BaseSection & {
  kind: 'scatter'
  title: string
  filters: {
    serial: string
    xMetric: string
    yMetric: string
    interval: string
    range: string
  }
  data: ScatterResp
}

export type HeatmapSection = BaseSection & {
  kind: 'heatmap'
  title: string
  filters: {
    serial: string
    interval: string
    aggregate: string
    range: string
    selectedMetrics: string[]
    diseaseKey?: string
    diseaseName?: string
  }
  data: RiskHeatmapResp
}

export type ReportSection = TimeseriesSection | ScatterSection | HeatmapSection

export type ChartsReport = {
  generatedAt: string
  houseId: string
  disease?: {
    key: string
    name: string
    metrics: string[]
  }
  sections: ReportSection[]
}
