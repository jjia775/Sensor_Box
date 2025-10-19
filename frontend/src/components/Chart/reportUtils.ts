import type { ChartsReport, ReportSection } from '../../types/report'
import formatTimestamp from '../../utils/formatTimestamp'

const CSS_STYLES = `
  body { font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; margin: 0; padding: 24px; background: #f9fafb; color: #111827; }
  h1 { font-size: 28px; margin-bottom: 8px; }
  h2 { font-size: 22px; margin: 32px 0 8px; }
  .meta { color: #4b5563; margin-bottom: 24px; font-size: 14px; }
  .section { background: white; border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); border: 1px solid #e5e7eb; }
  .section h3 { margin-top: 0; font-size: 18px; }
  .section img { max-width: 100%; border-radius: 12px; border: 1px solid #e5e7eb; margin: 16px 0; }
  .section table { border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }
  .section th, .section td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }
  .filters { font-size: 13px; color: #374151; background: #f3f4f6; padding: 12px; border-radius: 12px; }
  pre { background: #0f172a; color: #f8fafc; padding: 16px; border-radius: 12px; overflow-x: auto; font-size: 12px; }
`

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderFilters(section: ReportSection): string {
  if (section.kind === 'timeseries') {
    const { serial, metric, interval, aggregate, range } = section.filters
    return `Sensor: ${escapeHtml(serial)} | Metric: ${escapeHtml(metric)} | Interval: ${escapeHtml(interval)} | Aggregate: ${escapeHtml(aggregate)} | Range: ${escapeHtml(range)}`
  }
  if (section.kind === 'scatter') {
    const { serial, xMetric, yMetric, interval, range } = section.filters
    return `Sensor: ${escapeHtml(serial)} | X: ${escapeHtml(xMetric)} | Y: ${escapeHtml(yMetric)} | Interval: ${escapeHtml(interval)} | Range: ${escapeHtml(range)}`
  }
  const { serial, interval, aggregate, range, selectedMetrics, diseaseKey, diseaseName } = section.filters
  const disease = diseaseName || diseaseKey || 'N/A'
  const metrics = selectedMetrics.length ? selectedMetrics.map(escapeHtml).join(', ') : 'All metrics'
  return `Sensor: ${escapeHtml(serial)} | Disease: ${escapeHtml(disease)} | Interval: ${escapeHtml(interval)} | Aggregate: ${escapeHtml(aggregate)} | Range: ${escapeHtml(range)} | Metrics: ${metrics}`
}

function sectionToHtml(section: ReportSection): string {
  const title = escapeHtml(section.title)
  const filters = renderFilters(section)
  const image = `<img src="${section.imageDataUrl}" alt="${title}" />`
  const data = escapeHtml(JSON.stringify(section.data, null, 2))
  return `
    <div class="section">
      <h3>${title}</h3>
      <div class="filters">${filters}</div>
      ${image}
      <details>
        <summary>Raw data</summary>
        <pre>${data}</pre>
      </details>
    </div>
  `
}

export function buildChartsReportHtml(report: ChartsReport): string {
  const generatedAt = formatTimestamp(report.generatedAt) ?? report.generatedAt
  const diseaseInfo = report.disease
    ? `${escapeHtml(report.disease.name)} (${escapeHtml(report.disease.key)})`
    : 'N/A'
  const metrics = report.disease?.metrics?.length
    ? report.disease.metrics.map(escapeHtml).join(', ')
    : 'N/A'

  const sectionsHtml = report.sections.map(sectionToHtml).join('\n') || '<p>No chart data was captured.</p>'

  return `<!DOCTYPE html>
  <html lang="zh-CN">
    <head>
      <meta charSet="utf-8" />
      <title>Chart Report</title>
      <style>${CSS_STYLES}</style>
    </head>
    <body>
      <h1>Chart Report</h1>
      <div class="meta">Generated at: ${escapeHtml(generatedAt)} | House ID: ${escapeHtml(report.houseId || 'N/A')} | Disease: ${diseaseInfo} | Disease Metrics: ${metrics}</div>
      ${sectionsHtml}
    </body>
  </html>`
}

export function downloadChartsReport(report: ChartsReport) {
  const html = buildChartsReportHtml(report)
  const blob = new Blob([html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const filename = `chart-report-${report.houseId || 'house'}-${new Date(report.generatedAt).toISOString().replace(/[:.]/g, '-')}.html`
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
