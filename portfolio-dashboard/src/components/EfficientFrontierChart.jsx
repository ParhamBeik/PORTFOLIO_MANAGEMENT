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
  formatNumber,
  formatPercent,
  getRandomPortfolioSamples,
  normalizeRiskReturnPoint,
  thinChartPoints,
} from '../utils/portfolio'

function normalizePointList(items) {
  return items.map(normalizeRiskReturnPoint).filter(Boolean)
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
        {point.label ?? payload[0]?.name ?? 'پرتفوی'}
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

export function EfficientFrontierChart({
  efficientFrontier,
  optimalPortfolio,
  randomSamplesCloud,
}) {
  const randomPoints = thinChartPoints(
    normalizePointList(getRandomPortfolioSamples(randomSamplesCloud)),
  )
  const frontierPoints = normalizePointList(
    Array.isArray(efficientFrontier) ? efficientFrontier : [],
  ).sort((a, b) => a.risk - b.risk)
  const optimalPoint = normalizeRiskReturnPoint({
    risk: optimalPortfolio?.metrics?.volatility,
    return: optimalPortfolio?.metrics?.expected_return,
    sharpe: optimalPortfolio?.metrics?.sharpe_ratio,
    label: 'پرتفوی بهینه',
  })
  const chartData = [...randomPoints, ...frontierPoints, optimalPoint].filter(
    Boolean,
  )
  const risks = chartData.map((point) => point.risk)
  const returns = chartData.map((point) => point.return)
  const riskPadding = (Math.max(...risks) - Math.min(...risks)) * 0.08 || 0.002
  const returnPadding =
    (Math.max(...returns) - Math.min(...returns)) * 0.08 || 0.002

  return (
    <div className="h-[28rem]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={frontierPoints}
          margin={{ top: 16, right: 12, bottom: 18, left: 2 }}
        >
          <CartesianGrid stroke="#dbe4ee" strokeDasharray="4 4" />
          <XAxis
            allowDataOverflow
            dataKey="risk"
            domain={[
              Math.min(...risks) - riskPadding,
              Math.max(...risks) + riskPadding,
            ]}
            name="ریسک"
            tick={{ fill: '#475569', fontSize: 12 }}
            tickFormatter={formatPercent}
            tickLine={false}
            type="number"
          />
          <YAxis
            allowDataOverflow
            dataKey="return"
            domain={[
              Math.min(...returns) - returnPadding,
              Math.max(...returns) + returnPadding,
            ]}
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
            fillOpacity={0.22}
            line={false}
            name="پرتفوی‌های تصادفی"
            shape="circle"
          />
          <Line
            data={frontierPoints}
            dataKey="return"
            dot={{ r: 4, fill: '#0f766e', strokeWidth: 0 }}
            isAnimationActive={false}
            name="مرز کارا"
            stroke="#0f766e"
            strokeWidth={3}
            type="monotone"
          />
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
                position: 'top',
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
