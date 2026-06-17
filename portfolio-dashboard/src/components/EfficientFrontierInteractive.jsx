import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  createEfficientPortfolioSelection,
  extractWeightsFromEfficientPortfolio,
  formatNumber,
  formatPercent,
  getRandomPortfolioSamples,
  normalizeRiskReturnPoint,
  thinChartPoints,
} from '../utils/portfolio'

function normalizePointList(items) {
  return items.map(normalizeRiskReturnPoint).filter(Boolean)
}

function getPointDomain(points, key) {
  const values = points
    .map((point) => point[key])
    .filter((value) => typeof value === 'number' && Number.isFinite(value))

  if (!values.length) {
    return ['auto', 'auto']
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const padding = (max - min) * 0.08 || 0.002

  return [min - padding, max + padding]
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) {
    return null
  }

  const point = payload.find((item) => item.payload)?.payload

  if (!point) {
    return null
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 p-3 text-right text-xs shadow-lg">
      <p className="font-bold text-slate-950">
        {point.portfolioId
          ? `پرتفوی ${formatNumber(point.portfolioId, { maximumFractionDigits: 0 })}`
          : point.label ?? payload[0]?.name ?? 'پرتفوی'}
      </p>
      <p className="mt-2 text-slate-600">ریسک: {formatPercent(point.risk)}</p>
      <p className="mt-1 text-slate-600">
        بازده مورد انتظار: {formatPercent(point.return)}
      </p>
      {typeof point.sharpe === 'number' ? (
        <p className="mt-1 text-slate-600">
          نسبت شارپ: {formatNumber(point.sharpe)}
        </p>
      ) : null}
    </div>
  )
}

export function EfficientFrontierInteractive({
  efficientFrontier,
  optimalPortfolio,
  randomSamplesCloud,
  selectedPortfolio,
  onSelectPortfolio,
}) {
  const frontierSource = Array.isArray(efficientFrontier)
    ? efficientFrontier
    : []
  const randomPoints = thinChartPoints(
    normalizePointList(getRandomPortfolioSamples(randomSamplesCloud)),
  )
  const frontierPoints = normalizePointList(frontierSource).sort(
    (a, b) => a.risk - b.risk,
  )
  const optimalPoint = normalizeRiskReturnPoint({
    risk: optimalPortfolio?.metrics?.volatility,
    return: optimalPortfolio?.metrics?.expected_return,
    sharpe: optimalPortfolio?.metrics?.sharpe_ratio,
    label: 'پرتفوی بهینه',
  })
  const chartData = [...randomPoints, ...frontierPoints, optimalPoint].filter(
    Boolean,
  )
  const selectedFrontierPoint = frontierPoints.find(
    (point) => point.portfolioId === selectedPortfolio?.portfolioId,
  )

  function selectFrontierPoint(point) {
    if (!point?.source) {
      return
    }

    onSelectPortfolio(createEfficientPortfolioSelection(point.source))
  }

  function selectRandomPoint(point) {
    if (!point?.source) {
      return
    }

    const weights = extractWeightsFromEfficientPortfolio(point.source)

    if (!weights.length) {
      return
    }

    onSelectPortfolio({
      title: 'پرتفوی تصادفی انتخاب‌شده',
      portfolioId: point.source.portfolio_id,
      risk: point.risk,
      return: point.return,
      sharpe: point.sharpe,
      weights,
      sourceType: 'random',
    })
  }

  function renderFrontierDot({ cx, cy, payload }) {
    const isSelected = payload?.portfolioId === selectedPortfolio?.portfolioId

    return (
      <circle
        cx={cx}
        cy={cy}
        r={isSelected ? 6 : 4}
        fill={isSelected ? '#ec4899' : '#0f766e'}
        stroke={isSelected ? '#831843' : '#ffffff'}
        strokeWidth={isSelected ? 2 : 1}
        className="cursor-pointer transition"
        onClick={() => selectFrontierPoint(payload)}
        onMouseEnter={() => selectFrontierPoint(payload)}
      />
    )
  }

  return (
    <div className="h-[34rem] rounded-lg border border-slate-200 bg-white p-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={frontierPoints}
          margin={{ top: 16, right: 12, bottom: 18, left: 2 }}
        >
          <CartesianGrid stroke="#dbe4ee" strokeDasharray="4 4" />
          <XAxis
            allowDataOverflow
            dataKey="risk"
            domain={getPointDomain(chartData, 'risk')}
            name="ریسک"
            tick={{ fill: '#475569', fontSize: 12 }}
            tickFormatter={formatPercent}
            tickLine={false}
            type="number"
          />
          <YAxis
            allowDataOverflow
            dataKey="return"
            domain={getPointDomain(chartData, 'return')}
            name="بازده"
            tick={{ fill: '#475569', fontSize: 12 }}
            tickFormatter={formatPercent}
            tickLine={false}
            type="number"
            width={64}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend verticalAlign="top" height={32} />
          <Scatter
            data={randomPoints}
            fill="#94a3b8"
            fillOpacity={0.2}
            line={false}
            name="پرتفوی‌های تصادفی"
            onClick={selectRandomPoint}
            onMouseEnter={selectRandomPoint}
            shape="circle"
          />
          <Line
            data={frontierPoints}
            dataKey="return"
            dot={renderFrontierDot}
            activeDot={{
              r: 7,
              fill: '#f59e0b',
              stroke: '#78350f',
              strokeWidth: 2,
            }}
            isAnimationActive={false}
            name="مرز کارا"
            stroke="#0f766e"
            strokeWidth={3}
            type="monotone"
          />
          {selectedFrontierPoint ? (
            <ReferenceDot
              ifOverflow="extendDomain"
              r={8}
              x={selectedFrontierPoint.risk}
              y={selectedFrontierPoint.return}
              fill="#ec4899"
              stroke="#831843"
              strokeWidth={2}
              label={{
                value: 'انتخاب‌شده',
                position: 'top',
                fill: '#831843',
                fontSize: 12,
              }}
            />
          ) : null}
          {optimalPoint ? (
            <ReferenceDot
              ifOverflow="extendDomain"
              r={8}
              x={optimalPoint.risk}
              y={optimalPoint.return}
              fill="#f59e0b"
              stroke="#78350f"
              strokeWidth={2}
              label={{
                value: 'بهترین شارپ',
                position: 'bottom',
                fill: '#78350f',
                fontSize: 12,
              }}
            />
          ) : null}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
