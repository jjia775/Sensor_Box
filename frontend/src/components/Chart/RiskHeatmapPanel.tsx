import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { MetricInfo, MetricsResp, RiskHeatmapResp } from '../../types/charts'
import type { Sensor } from '../../types/sensors'
import formatTimestamp, { parseTimestampParts } from '../../utils/formatTimestamp'
import { METRIC_LABELS } from './config'
import { formatISO, getSerial } from './utils'
import type { HeatmapSection } from '../../types/report'

type RangeOpt = '6h' | '12h' | '24h' | '48h'
type Agg = 'avg' | 'min' | 'max' | 'last' | 'sum'

type Props = {
  apiBase: string
  houseId: string
  diseaseKey?: string
  diseaseName?: string
  allowedMetrics?: string[]
}

export type RiskHeatmapPanelHandle = {
  getReportSection: () => Promise<HeatmapSection | null>
}

const DISABLED_COLOR = '#c4b5fd'
const NO_SENSOR_COLOR = '#d1d5db'
const NO_DATA_COLOR = '#f3f4f6'

const TITLE_FONT = "'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif"
const pad = (value: number): string => value.toString().padStart(2, '0')

type HeatmapRenderOptions = {
  serial: string
  interval: string
  agg: Agg
  range: RangeOpt
  diseaseKey?: string
  diseaseName?: string
  selectedMetrics: string[]
}

function renderHeatmapToCanvas(
  canvas: HTMLCanvasElement,
  data: RiskHeatmapResp,
  options: HeatmapRenderOptions,
) {
  if (!data.labels.length || !data.rows.length) {
    return false
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) return false

  const { serial, interval, agg, range, diseaseKey, diseaseName, selectedMetrics } = options

  const width = 1400
  const height = 900
  canvas.width = width
  canvas.height = height

  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)

  const marginLeft = 260
  const marginRight = 240
  const marginBottom = 160
  let marginTop = 220

  const metricName = (metric: string) => METRIC_LABELS[metric] ?? metric.toUpperCase()

  let headerY = 80
  ctx.fillStyle = '#111827'
  ctx.font = `bold 34px ${TITLE_FONT}`
  const title = data.title || 'Risk Heatmap'
  ctx.fillText(title, marginLeft, headerY)
  headerY += 42

  ctx.font = `20px ${TITLE_FONT}`
  const timeWindow = `${formatDateLabel(data.start)} ~ ${formatDateLabel(data.end)}`.trim()
  if (timeWindow.trim()) {
    ctx.fillStyle = '#4b5563'
    ctx.fillText(timeWindow, marginLeft, headerY)
    headerY += 32
  }

  ctx.fillStyle = '#374151'
  ctx.font = `18px ${TITLE_FONT}`
  const filters: string[] = []
  filters.push(`Sensor: ${serial || 'N/A'}`)
  if (diseaseName || diseaseKey) {
    filters.push(`Disease: ${diseaseName || diseaseKey}`)
  }
  filters.push(`Interval: ${interval}`)
  filters.push(`Aggregate: ${agg}`)
  filters.push(`Range: ${formatRangeLabel(range)}`)

  const metricsLabel = selectedMetrics.length
    ? selectedMetrics.map(metricName).join(', ')
    : data.rows.map(r => metricName(r.metric)).join(', ')

  const filterText = `${filters.join(' | ')}`
  const filterLines = wrapText(ctx, filterText, marginLeft, headerY, width - marginLeft - marginRight, 26)
  headerY += filterLines * 26 + 12
  ctx.font = `16px ${TITLE_FONT}`
  ctx.fillStyle = '#4b5563'
  const metricsLines = wrapText(
    ctx,
    `Metrics: ${metricsLabel || 'All available metrics'}`,
    marginLeft,
    headerY,
    width - marginLeft - marginRight,
    24,
  )
  headerY += metricsLines * 24

  marginTop = Math.max(marginTop, headerY + 40)

  const margin = { top: marginTop, right: marginRight, bottom: marginBottom, left: marginLeft }
  const gridWidth = width - margin.left - margin.right
  const gridHeight = height - margin.top - margin.bottom
  const cols = data.labels.length
  const rowsCount = data.rows.length
  const cellWidth = gridWidth / Math.max(cols, 1)
  const cellHeight = gridHeight / Math.max(rowsCount, 1)

  ctx.save()
  ctx.translate(margin.left - 120, margin.top + gridHeight / 2)
  ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'
  ctx.font = `bold 20px ${TITLE_FONT}`
  ctx.fillStyle = '#111827'
  ctx.fillText('Parameter', 0, 0)
  ctx.restore()

  ctx.textAlign = 'center'
  ctx.font = `bold 20px ${TITLE_FONT}`
  ctx.fillText('Time (HH:MM)', margin.left + gridWidth / 2, height - margin.bottom + 80)

  ctx.strokeStyle = '#d1d5db'
  ctx.lineWidth = 1
  for (let i = 0; i <= rowsCount; i += 1) {
    const y = margin.top + i * cellHeight
    ctx.beginPath()
    ctx.moveTo(margin.left, y)
    ctx.lineTo(margin.left + gridWidth, y)
    ctx.stroke()
  }
  for (let i = 0; i <= cols; i += 1) {
    const x = margin.left + i * cellWidth
    ctx.beginPath()
    ctx.moveTo(x, margin.top)
    ctx.lineTo(x, margin.top + gridHeight)
    ctx.stroke()
  }

  data.rows.forEach((row, rowIdx) => {
    const y = margin.top + rowIdx * cellHeight
    const centerY = y + cellHeight / 2
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.font = `16px ${TITLE_FONT}`
    ctx.fillStyle = '#111827'
    const baseLabel = metricName(row.metric)
    const unitLabel = row.unit ? ` (${row.unit})` : ''
    ctx.fillText(`${baseLabel}${unitLabel}`, margin.left - 18, centerY)
    data.labels.forEach((_, colIdx) => {
      const x = margin.left + colIdx * cellWidth
      const value = row.values[colIdx]
      const risk = clampRisk(row.risk[colIdx])
      let fill = NO_DATA_COLOR
      let text: string | null = null
      if (!row.has_sensor) {
        fill = NO_SENSOR_COLOR
        text = null
      } else if (!row.enabled) {
        fill = DISABLED_COLOR
        text = null
      } else if (value == null || risk == null) {
        fill = NO_DATA_COLOR
        text = null
      } else {
        fill = colorForRisk(risk)
        text = value == null ? null : `${value.toFixed(1)}`
      }
      ctx.fillStyle = fill
      ctx.fillRect(x, y, cellWidth, cellHeight)
      ctx.strokeStyle = '#ffffff'
      ctx.strokeRect(x, y, cellWidth, cellHeight)

      const shouldShowText = !!text && cellHeight >= 32 && cellWidth >= 80
      if (shouldShowText && text) {
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        const fontSize = Math.min(24, Math.max(12, Math.min(cellHeight, cellWidth) * 0.35))
        ctx.font = `bold ${fontSize}px ${TITLE_FONT}`
        ctx.fillStyle = '#111827'
        ctx.fillText(text, x + cellWidth / 2, centerY)
      }
    })
  })

  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.font = `14px ${TITLE_FONT}`
  const maxXTicks = 12
  const tickEvery = Math.max(1, Math.ceil(cols / maxXTicks))
  const drawnTicks = new Set<number>()
  for (let col = 0; col < cols; col += tickEvery) {
    const x = margin.left + col * cellWidth + cellWidth / 2
    const parts = parseTimestampParts(data.labels[col])
    let dateLabel: string
    let timeLabel: string
    if (parts) {
      dateLabel = `${parts.month}/${parts.day}`
      timeLabel = `${pad(parts.hour)}:${pad(parts.minute)}`
    } else {
      const ts = new Date(data.labels[col])
      dateLabel = `${ts.getMonth() + 1}/${ts.getDate()}`
      timeLabel = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}`
    }
    ctx.fillStyle = '#4b5563'
    ctx.fillText(dateLabel, x, margin.top + gridHeight + 10)
    ctx.fillText(timeLabel, x, margin.top + gridHeight + 28)
    drawnTicks.add(col)
  }
  if (!drawnTicks.has(cols - 1)) {
    const col = cols - 1
    const x = margin.left + col * cellWidth + cellWidth / 2
    const parts = parseTimestampParts(data.labels[col])
    let dateLabel: string
    let timeLabel: string
    if (parts) {
      dateLabel = `${parts.month}/${parts.day}`
      timeLabel = `${pad(parts.hour)}:${pad(parts.minute)}`
    } else {
      const ts = new Date(data.labels[col])
      dateLabel = `${ts.getMonth() + 1}/${ts.getDate()}`
      timeLabel = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}`
    }
    ctx.fillStyle = '#4b5563'
    ctx.fillText(dateLabel, x, margin.top + gridHeight + 10)
    ctx.fillText(timeLabel, x, margin.top + gridHeight + 28)
  }

  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  const legendX = margin.left + gridWidth + 40
  let legendY = margin.top - 10
  ctx.font = `bold 18px ${TITLE_FONT}`
  ctx.fillStyle = '#111827'
  ctx.fillText('Risk Level', legendX, legendY)
  legendY += 20

  const gradientHeight = 220
  const gradient = ctx.createLinearGradient(0, legendY, 0, legendY + gradientHeight)
  gradient.addColorStop(0, colorForRisk(1))
  gradient.addColorStop(0.5, colorForRisk(0.5))
  gradient.addColorStop(1, colorForRisk(0))
  ctx.fillStyle = gradient
  ctx.fillRect(legendX, legendY, 24, gradientHeight)

  ctx.save()
  ctx.strokeStyle = '#6b7280'
  ctx.lineWidth = 1
  ctx.strokeRect(legendX, legendY, 24, gradientHeight)
  ctx.restore()
  legendY += gradientHeight + 24

  const statusLegend = [
    { color: DISABLED_COLOR, label: 'Sensor disabled' },
    { color: NO_SENSOR_COLOR, label: 'No matching sensor' },
    { color: NO_DATA_COLOR, label: 'No data in range' },
  ]
  ctx.textBaseline = 'middle'
  ctx.font = `14px ${TITLE_FONT}`
  statusLegend.forEach(item => {
    ctx.fillStyle = item.color
    ctx.fillRect(legendX, legendY, 18, 18)
    ctx.strokeStyle = '#9ca3af'
    ctx.strokeRect(legendX, legendY, 18, 18)
    ctx.fillStyle = '#374151'
    ctx.fillText(item.label, legendX + 28, legendY + 9)
    legendY += 28
  })

  ctx.strokeStyle = '#9ca3af'
  ctx.strokeRect(margin.left, margin.top, gridWidth, gridHeight)

  return true
}

function formatRangeLabel(range: RangeOpt) {
  if (range === '6h') return 'Last 6 hours'
  if (range === '12h') return 'Last 12 hours'
  if (range === '48h') return 'Last 48 hours'
  return 'Last 24 hours'
}

function formatDateLabel(value?: string | null) {
  if (!value) return ''
  const parts = parseTimestampParts(value)
  if (parts) {
    return `${parts.year}-${pad(parts.month)}-${pad(parts.day)} ${pad(parts.hour)}:${pad(parts.minute)}`
  }
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(
    dt.getHours(),
  ).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
) {
  const words = text.split(/\s+/)
  let line = ''
  let cursorY = y
  const lines: string[] = []
  for (const word of words) {
    const test = line ? `${line} ${word}` : word
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line)
      line = word
    } else {
      line = test
    }
  }
  if (line) {
    lines.push(line)
  }
  lines.forEach((ln, idx) => {
    ctx.fillText(ln, x, cursorY + idx * lineHeight)
  })
  return lines.length
}

function getRangeMs(range: RangeOpt) {
  if (range === '6h') return 6 * 3600_000
  if (range === '12h') return 12 * 3600_000
  if (range === '48h') return 48 * 3600_000
  return 24 * 3600_000
}

function clampRisk(risk: number | null | undefined) {
  if (risk == null || Number.isNaN(risk)) return null
  if (risk < 0) return 0
  if (risk > 1) return 1
  return risk
}

function colorForRisk(risk: number) {
  const hue = 120 - risk * 120 // 120 = green, 0 = red
  const lightness = 65 - risk * 20
  return `hsl(${hue}, 85%, ${lightness}%)`
}

const RiskHeatmapPanel = forwardRef<RiskHeatmapPanelHandle, Props>(
  ({ apiBase, houseId, diseaseKey, diseaseName, allowedMetrics }, ref) => {
  const [serials, setSerials] = useState<string[]>([])
  const [serial, setSerial] = useState<string>('')

  const [interval, setInterval] = useState<string>('1h')
  const [agg, setAgg] = useState<Agg>('avg')
  const [range, setRange] = useState<RangeOpt>('24h')

  const [allMetrics, setAllMetrics] = useState<MetricInfo[]>([])
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<RiskHeatmapResp | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Fetch all metrics
  useEffect(() => {
    let alive = true
    fetch(`${apiBase}/api/charts/metrics`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((resp: MetricsResp) => {
        if (!alive) return
        setAllMetrics(resp.metrics || [])
      })
      .catch(() => setAllMetrics([]))
    return () => {
      alive = false
    }
  }, [apiBase])

  // Filter metrics according to allowedMetrics
  const filteredMetrics = useMemo<MetricInfo[]>(() => {
    if (!allMetrics?.length) return []
    if (!allowedMetrics || allowedMetrics.length === 0) return allMetrics
    const allow = new Set(allowedMetrics.map(m => m.toLowerCase()))
    return allMetrics.filter(m => allow.has(m.metric))
  }, [allMetrics, allowedMetrics])

  // Initialize the selected metrics
  useEffect(() => {
    const validSet = new Set(filteredMetrics.map(m => m.metric))
    setSelectedMetrics(prev => {
      const kept = prev.filter(m => validSet.has(m))
      if (kept.length > 0) return kept
      return filteredMetrics.map(m => m.metric)
    })
  }, [filteredMetrics])

  // Fetch sensors
  useEffect(() => {
    if (!houseId) {
      setSerials([])
      setSerial('')
      return
    }
    fetch(`${apiBase}/sensors/?house_id=${encodeURIComponent(houseId)}`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((arr: Sensor[]) => {
        const uniq: string[] = []
        const seen = new Set<string>()
        for (const s of arr) {
          const sn = getSerial(s)
          if (sn && !seen.has(sn)) {
            seen.add(sn)
            uniq.push(sn)
          }
        }
        setSerials(uniq)
        const key = `sensor_serial:${houseId}:heatmap`
        const prev = localStorage.getItem(key)
        const initial = prev && uniq.includes(prev) ? prev : uniq[0] || ''
        setSerial(initial)
      })
      .catch(() => {
        setSerials([])
        setSerial('')
      })
  }, [apiBase, houseId])

  const noMetricReason = useMemo(() => {
    if ((allMetrics?.length || 0) === 0) return 'Failed to load available metrics'
    if (allowedMetrics && allowedMetrics.length > 0 && filteredMetrics.length === 0) return 'The selected disease is not associated with any metrics'
    return ''
  }, [allMetrics, allowedMetrics, filteredMetrics])

  const handleMetricToggle = (metric: string, checked: boolean) => {
    setSelectedMetrics(prev => {
      if (checked) {
        if (prev.includes(metric)) return prev
        return [...prev, metric]
      }
      return prev.filter(m => m !== metric)
    })
  }

  const selectAll = () => {
    setSelectedMetrics(filteredMetrics.map(m => m.metric))
  }

  const clearAll = () => {
    setSelectedMetrics([])
  }

  const loadHeatmap = async () => {
    setLoading(true)
    setError(null)
    setData(null)
    try {
      if (!serial) throw new Error('No sensor serial available')
      if (!selectedMetrics.length && (!allowedMetrics || allowedMetrics.length === 0)) {
        throw new Error('Please select at least one metric')
      }
      const now = new Date()
      const end = now
      const start = new Date(now.getTime() - getRangeMs(range))
      const payload: Record<string, any> = {
        serial_number: serial,
        start_ts: formatISO(start),
        end_ts: formatISO(end),
        interval,
        agg,
        title: `Risk Heatmap (${interval}, ${agg})`,
      }
      if (selectedMetrics.length > 0) {
        payload.metrics = selectedMetrics
      }
      if (diseaseKey) {
        payload.disease_key = diseaseKey
      }
      const r = await fetch(`${apiBase}/api/charts/risk_heatmap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())
      const resp: RiskHeatmapResp = await r.json()
      setData(resp)
      localStorage.setItem(`sensor_serial:${houseId}:heatmap`, serial)
    } catch (e: any) {
      setError(e?.message || 'Failed to load heatmap')
    } finally {
      setLoading(false)
    }
  }

  const buildHeatmapImage = useCallback(() => {
    if (!data || !canvasRef.current) return null
    const canvas = canvasRef.current
    const ok = renderHeatmapToCanvas(canvas, data, {
      serial,
      interval,
      agg,
      range,
      diseaseKey,
      diseaseName,
      selectedMetrics,
    })
    if (!ok) return null
    return canvas.toDataURL('image/png')
  }, [agg, data, diseaseKey, diseaseName, interval, range, selectedMetrics, serial])

  const downloadHeatmapImage = useCallback(() => {
    if (!data) return
    const image = buildHeatmapImage()
    if (!image) return
    const link = document.createElement('a')
    const startLabel = data.start ? data.start.replace(/[:T]/g, '-').slice(0, 16) : 'heatmap'
    link.download = `risk-heatmap-${serial || 'sensor'}-${startLabel}.png`
    link.href = image
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [buildHeatmapImage, data, serial])

  const renderCell = (rowIndex: number, colIndex: number) => {
    if (!data) return null
    const row = data.rows[rowIndex]
    const rawRisk = clampRisk(row.risk[colIndex])
    const value = row.values[colIndex]

    if (!row.has_sensor) {
      return (
        <div className="h-full w-full rounded-md px-2 py-1 text-xs font-medium" style={{ backgroundColor: NO_SENSOR_COLOR, color: '#374151' }}>
          No sensor
        </div>
      )
    }
    if (!row.enabled) {
      return (
        <div className="h-full w-full rounded-md px-2 py-1 text-xs font-medium" style={{ backgroundColor: DISABLED_COLOR, color: '#312e81' }}>
          Disabled
        </div>
      )
    }
    if (value == null || rawRisk == null) {
      return (
        <div className="h-full w-full rounded-md px-2 py-1 text-xs" style={{ backgroundColor: NO_DATA_COLOR, color: '#6b7280' }}>
          No data
        </div>
      )
    }
    const bg = colorForRisk(rawRisk)
    return (
      <div className="h-full w-full rounded-md px-2 py-1 text-xs" style={{ backgroundColor: bg, color: '#111827' }}>
        <div className="font-semibold">{value.toFixed(1)}</div>
        <div className="text-[10px] text-gray-700">Risk {(rawRisk * 100).toFixed(0)}%</div>
      </div>
    )
  }

  useImperativeHandle(
    ref,
    () => ({
      async getReportSection() {
        if (!data) return null
        const imageDataUrl = buildHeatmapImage()
        if (!imageDataUrl) return null
        return {
          kind: 'heatmap',
          title: data.title,
          imageDataUrl,
          filters: {
            serial,
            interval,
            aggregate: agg,
            range,
            selectedMetrics: selectedMetrics.length > 0 ? selectedMetrics : data.rows.map(r => r.metric),
            diseaseKey,
            diseaseName,
          },
          data,
        }
      },
    }),
    [agg, buildHeatmapImage, data, diseaseKey, diseaseName, interval, range, selectedMetrics, serial],
  )

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-lg font-semibold">Risk Heatmap</div>
          {data?.start && data?.end && (
            <div className="text-xs text-gray-500">
              {formatTimestamp(data.start)} ~ {formatTimestamp(data.end)}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
          <div>
            <label className="block text-sm font-medium mb-1">Sensor Serial</label>
            <select className="w-full rounded-xl border px-3 py-2" value={serial} onChange={e => setSerial(e.target.value)}>
              {serials.length === 0 && <option value="">No serials</option>}
              {serials.map(sn => (
                <option key={sn} value={sn}>{sn}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Interval</label>
            <select className="w-full rounded-xl border px-3 py-2" value={interval} onChange={e => setInterval(e.target.value)}>
              <option value="30m">30m</option>
              <option value="1h">1h</option>
              <option value="2h">2h</option>
              <option value="6h">6h</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Aggregate</label>
            <select className="w-full rounded-xl border px-3 py-2" value={agg} onChange={e => setAgg(e.target.value as Agg)}>
              <option value="avg">avg</option>
              <option value="min">min</option>
              <option value="max">max</option>
              <option value="last">last</option>
              <option value="sum">sum</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Range</label>
            <select className="w-full rounded-xl border px-3 py-2" value={range} onChange={e => setRange(e.target.value as RangeOpt)}>
              <option value="6h">Last 6h</option>
              <option value="12h">Last 12h</option>
              <option value="24h">Last 24h</option>
              <option value="48h">Last 48h</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium mb-1">Metrics</label>
            <div className="flex flex-wrap gap-2">
              {filteredMetrics.map(m => {
                const checked = selectedMetrics.includes(m.metric)
                return (
                  <label key={m.metric} className={`flex items-center gap-1 rounded-full border px-3 py-1 text-xs ${checked ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-100'}`}>
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={checked}
                      onChange={e => handleMetricToggle(m.metric, e.target.checked)}
                    />
                    <span>{METRIC_LABELS[m.metric] ?? m.metric.toUpperCase()}</span>
                  </label>
                )
              })}
              {filteredMetrics.length === 0 && (
                <span className="text-xs text-gray-500">No available metrics</span>
              )}
            </div>
            {noMetricReason && (
              <div className="mt-1 text-xs text-amber-700">{noMetricReason}</div>
            )}
            <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-500">
              <button type="button" className="underline" onClick={selectAll}>Select all</button>
              <button type="button" className="underline" onClick={clearAll}>Clear all</button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={downloadHeatmapImage}
            disabled={!data || !data.labels.length || loading}
            className="rounded-xl border px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Download PNG
          </button>
          <button
            onClick={loadHeatmap}
            disabled={!serial || loading || filteredMetrics.length === 0 || (selectedMetrics.length === 0 && (!allowedMetrics || allowedMetrics.length === 0))}
            className="rounded-xl bg-black text-white px-4 py-2 disabled:opacity-60"
          >
            {loading ? 'Loading...' : 'Load Heatmap'}
          </button>
        </div>

        {error && <div className="mt-3 rounded-xl border bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      </div>

      {data && data.labels.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm overflow-x-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="text-lg font-semibold">{data.title}</div>
            <div className="text-sm text-gray-500">Interval: {data.interval}</div>
          </div>
          <table className="min-w-[720px] border-collapse">
            <thead>
              <tr className="text-xs text-gray-500">
                <th className="sticky left-0 bg-white/95 backdrop-blur border-b border-gray-100 px-3 py-2 text-left">Metric</th>
                {data.labels.map((label, idx) => {
                  const parts = parseTimestampParts(label)
                  const display = parts
                    ? `${parts.month}/${parts.day} ${pad(parts.hour)}:${pad(parts.minute)}`
                    : (() => {
                        const ts = new Date(label)
                        return `${ts.getMonth() + 1}/${ts.getDate()} ${String(ts.getHours()).padStart(2, '0')}:${String(
                          ts.getMinutes(),
                        ).padStart(2, '0')}`
                      })()
                  return (
                    <th key={idx} className="border-b border-gray-100 px-2 py-2 text-center font-normal">
                      {display}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, rowIdx) => (
                <tr key={row.metric} className="align-top text-xs">
                  <td className="sticky left-0 bg-white/95 backdrop-blur border-t border-gray-100 px-3 py-2">
                    <div className="font-semibold text-gray-800">{METRIC_LABELS[row.metric] ?? row.metric.toUpperCase()}</div>
                    <div className="text-[11px] text-gray-500">Unit: {row.unit || '-'}</div>
                    <div className="mt-1 text-[10px] text-gray-400">
                      {row.has_sensor ? (row.enabled ? 'Sensor active' : 'Sensor disabled') : 'Sensor not installed'}
                    </div>
                  </td>
                  {data.labels.map((_, colIdx) => (
                    <td key={`${row.metric}-${colIdx}`} className="border-t border-gray-100 px-1 py-1 align-middle">
                      {renderCell(rowIdx, colIdx)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-4 grid gap-2 text-[11px] text-gray-500 md:grid-cols-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: colorForRisk(0) }} />
              Low risk
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: colorForRisk(0.5) }} />
              Medium risk
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: colorForRisk(1) }} />
              High risk
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: DISABLED_COLOR }} />
              Sensor disabled
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: NO_SENSOR_COLOR }} />
              No matching sensor
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded" style={{ backgroundColor: NO_DATA_COLOR }} />
              No data in range
            </div>
          </div>
        </div>
      )}

      <canvas ref={canvasRef} style={{ display: 'none' }} aria-hidden="true" />

      {data && data.labels.length === 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white/90 p-6 text-center text-sm text-gray-500">
          Heatmap returned no data. Adjust the time range or choose other metrics.
        </div>
      )}
    </div>
  )
})

export default RiskHeatmapPanel
