import type { ScatterPoint, Threshold } from '../../types/charts'

const LEGEND_BOX_SIZE = 10
const X_THRESHOLD_COLOR = '#ef4444'
const Y_THRESHOLD_COLOR = '#3b82f6'

export default function ScatterPlotSVG({
  title,
  unitX,
  unitY,
  points,
  bestFit,
  xThresholds,
  yThresholds,
}: {
  title: string
  unitX: string
  unitY: string
  points: ScatterPoint[]
  bestFit: { slope: number; intercept: number } | null
  xThresholds: Threshold[]
  yThresholds: Threshold[]
}) {
  const width = 900
  const height = 360
  const padding = { left: 70, right: 20, top: 40, bottom: 60 }

  if (!points.length) {
    return (
      <div className="rounded-2xl bg-white border shadow p-4">
        <div className="text-lg font-semibold mb-1">{title}</div>
        <div className="text-sm text-gray-500">No data.</div>
      </div>
    )
  }

  const allX = points.map(p => p.x)
  const allY = points.map(p => p.y)
  const thresholdX = xThresholds.map(t => t.value)
  const thresholdY = yThresholds.map(t => t.value)
  const minX = Math.min(...allX, ...(thresholdX.length ? thresholdX : [Infinity]))
  const maxX = Math.max(...allX, ...(thresholdX.length ? thresholdX : [-Infinity]))
  const minY = Math.min(...allY, ...(thresholdY.length ? thresholdY : [Infinity]))
  const maxY = Math.max(...allY, ...(thresholdY.length ? thresholdY : [-Infinity]))

  const padRange = (min: number, max: number) => {
    if (!isFinite(min) || !isFinite(max)) {
      return [min, max]
    }
    if (min === max) {
      const delta = Math.abs(min || 1)
      return [min - delta * 0.1, max + delta * 0.1]
    }
    const span = max - min
    const extra = span * 0.05
    return [min - extra, max + extra]
  }

  const [x0, x1] = padRange(minX, maxX)
  const [y0, y1] = padRange(minY, maxY)

  const xscale = (v: number) =>
    padding.left + ((v - x0) / Math.max(1e-9, x1 - x0)) * (width - padding.left - padding.right)
  const yscale = (v: number) =>
    padding.top + (1 - (v - y0) / Math.max(1e-9, y1 - y0)) * (height - padding.top - padding.bottom)

  const xTicks = 6
  const yTicks = 6
  const tickValsX = Array.from({ length: xTicks }, (_, i) => x0 + (i * (x1 - x0)) / (xTicks - 1))
  const tickValsY = Array.from({ length: yTicks }, (_, i) => y0 + (i * (y1 - y0)) / (yTicks - 1))

  const bestFitLine = (() => {
    if (!bestFit) return null
    const xStart = x0
    const xEnd = x1
    const yStart = bestFit.intercept + bestFit.slope * xStart
    const yEnd = bestFit.intercept + bestFit.slope * xEnd
    return {
      x1: xscale(xStart),
      y1: yscale(yStart),
      x2: xscale(xEnd),
      y2: yscale(yEnd),
    }
  })()

  return (
    <div className="rounded-2xl bg-white border shadow p-4 overflow-x-auto">
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-semibold">{title}</div>
        <div className="text-sm text-gray-500">
          {unitX && <span className="mr-4">X Unit: {unitX}</span>}
          {unitY && <span>Y Unit: {unitY}</span>}
        </div>
      </div>
      <svg width={width} height={height}>
        <rect x={0} y={0} width={width} height={height} fill="white" />
        {tickValsY.map((v, idx) => {
          const y = yscale(v)
          return (
            <g key={`grid-y-${idx}`}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} stroke="#f3f4f6" />
              <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#6b7280">
                {Number.isFinite(v) ? v.toFixed(2) : 'n/a'}
              </text>
            </g>
          )
        })}
        {tickValsX.map((v, idx) => {
          const x = xscale(v)
          return (
            <g key={`grid-x-${idx}`}>
              <line x1={x} x2={x} y1={padding.top} y2={height - padding.bottom} stroke="#f3f4f6" />
              <text x={x} y={height - padding.bottom + 16} textAnchor="middle" fontSize={10} fill="#6b7280">
                {Number.isFinite(v) ? v.toFixed(2) : 'n/a'}
              </text>
            </g>
          )
        })}

        {/* Axis */}
        <line x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} stroke="#e5e7eb" />
        <line x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} stroke="#e5e7eb" />

        {/* Threshold lines */}
        {xThresholds.map((t, idx) => {
          const x = xscale(t.value)
          return (
            <g key={`x-thr-${idx}`}>
              <line
                x1={x}
                x2={x}
                y1={padding.top}
                y2={height - padding.bottom}
                stroke={X_THRESHOLD_COLOR}
                strokeDasharray="4 4"
              />
              <text x={x + 4} y={padding.top + 12} fontSize={10} fill="#6b7280" textAnchor="start">
                {t.label}: {t.value}
              </text>
            </g>
          )
        })}
        {yThresholds.map((t, idx) => {
          const y = yscale(t.value)
          return (
            <g key={`y-thr-${idx}`}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                stroke={Y_THRESHOLD_COLOR}
                strokeDasharray="4 4"
              />
              <text x={width - padding.right} y={y - 4} fontSize={10} fill="#6b7280" textAnchor="end">
                {t.label}: {t.value}
              </text>
            </g>
          )
        })}

        {/* Points */}
        {points.map((p, idx) => (
          <circle
            key={`pt-${idx}`}
            cx={xscale(p.x)}
            cy={yscale(p.y)}
            r={4}
            fill="#f97316"
            stroke="#c2410c"
            strokeWidth={1}
          >
            <title>{`${p.ts}\nX=${p.x.toFixed(3)}, Y=${p.y.toFixed(3)}`}</title>
          </circle>
        ))}

        {/* Best fit line */}
        {bestFitLine && (
          <line
            x1={bestFitLine.x1}
            y1={bestFitLine.y1}
            x2={bestFitLine.x2}
            y2={bestFitLine.y2}
            stroke="#2563eb"
            strokeWidth={2}
          />
        )}

        {/* Axis labels */}
        <text
          x={(padding.left + width - padding.right) / 2}
          y={height - padding.bottom + 36}
          textAnchor="middle"
          fontSize={12}
          fill="#374151"
        >
          {unitX ? `X (${unitX})` : 'X'}
        </text>
        <text
          transform={`translate(${padding.left - 48}, ${(padding.top + height - padding.bottom) / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize={12}
          fill="#374151"
        >
          {unitY ? `Y (${unitY})` : 'Y'}
        </text>

        {/* Legend */}
        <g transform={`translate(${width - padding.right - 160}, ${padding.top})`}>
          <g className="legend-observations">
            <rect width={LEGEND_BOX_SIZE} height={LEGEND_BOX_SIZE} fill="#f97316" stroke="#c2410c" strokeWidth={1} />
            <text x={LEGEND_BOX_SIZE + 6} y={LEGEND_BOX_SIZE - 1} fontSize={11} fill="#374151">
              Observations
            </text>
          </g>
          <g transform="translate(0, 18)" className="legend-trend">
            <line
              x1={0}
              x2={LEGEND_BOX_SIZE}
              y1={LEGEND_BOX_SIZE / 2}
              y2={LEGEND_BOX_SIZE / 2}
              stroke="#2563eb"
              strokeWidth={2}
            />
            <text x={LEGEND_BOX_SIZE + 6} y={LEGEND_BOX_SIZE / 2 + 3} fontSize={11} fill="#374151">
              Trend
            </text>
          </g>
        </g>
      </svg>
    </div>
  )
}
