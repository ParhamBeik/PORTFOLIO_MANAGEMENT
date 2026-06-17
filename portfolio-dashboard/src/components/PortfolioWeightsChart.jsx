import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatPercent } from '../utils/portfolio'

export function PortfolioWeightsChart({ weights }) {
  const chartData = weights.map((item) => ({
    ...item,
    weightDecimal: item.weight / 100,
  }))

  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          margin={{ top: 8, right: 8, bottom: 20, left: 4 }}
        >
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" vertical={false} />
          <XAxis
            dataKey="symbol"
            interval={0}
            tick={{ fill: '#334155', fontSize: 12 }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 0.3]}
            tickFormatter={formatPercent}
            tick={{ fill: '#64748b', fontSize: 12 }}
            tickLine={false}
            width={58}
          />
          <Tooltip
            cursor={{ fill: 'rgba(16,185,129,0.08)' }}
            formatter={(value) => [formatPercent(value), 'وزن']}
            labelFormatter={(label) => `نماد: ${label}`}
          />
          <Bar
            dataKey="weightDecimal"
            fill="#059669"
            maxBarSize={42}
            name="وزن"
            radius={[8, 8, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
