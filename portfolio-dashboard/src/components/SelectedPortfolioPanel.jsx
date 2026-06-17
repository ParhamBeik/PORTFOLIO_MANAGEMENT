import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import {
  formatDash,
  formatNumber,
  formatPercent,
  normalizeWeightArray,
} from '../utils/portfolio'

const COLORS = [
  '#0f766e',
  '#059669',
  '#10b981',
  '#14b8a6',
  '#0ea5e9',
  '#2563eb',
  '#6366f1',
  '#8b5cf6',
  '#f59e0b',
  '#ef4444',
]

export function SelectedPortfolioPanel({ selectedPortfolio }) {
  const weights = normalizeWeightArray(selectedPortfolio?.weights)
  const activeWeights = weights.filter((item) => item.weight > 0)

  return (
    <aside className="h-full rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="rounded-lg bg-slate-950 p-4 text-white shadow-lg">
        <p className="text-xs font-bold text-emerald-300">پرتفوی انتخاب‌شده</p>
        <h3 className="mt-2 text-xl font-black">
          {selectedPortfolio?.title ?? 'پرتفوی'}
        </h3>
        {selectedPortfolio?.portfolioId ? (
          <p className="mt-2 text-sm text-slate-300">
            شناسه پرتفوی: {formatNumber(selectedPortfolio.portfolioId, {
              maximumFractionDigits: 0,
            })}
          </p>
        ) : (
          <p className="mt-2 text-sm text-slate-300">پرتفوی بهینه اصلی</p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs text-slate-500">ریسک</p>
          <strong className="mt-1 block text-sm text-slate-950">
            {formatDash(selectedPortfolio?.risk, formatPercent)}
          </strong>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs text-slate-500">بازده</p>
          <strong className="mt-1 block text-sm text-slate-950">
            {formatDash(selectedPortfolio?.return, formatPercent)}
          </strong>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs text-slate-500">شارپ</p>
          <strong className="mt-1 block text-sm text-slate-950">
            {formatDash(selectedPortfolio?.sharpe, (value) =>
              formatNumber(value, { maximumFractionDigits: 4 }),
            )}
          </strong>
        </div>
      </div>

      <div className="mt-5 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={activeWeights}
              dataKey="weightDecimal"
              innerRadius="58%"
              outerRadius="86%"
              nameKey="symbol"
              paddingAngle={2}
            >
              {activeWeights.map((item, index) => (
                <Cell
                  key={item.symbol}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => [formatPercent(value), 'وزن']}
              labelFormatter={(label) => `نماد: ${label}`}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 max-h-80 overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full border-collapse text-right text-sm">
          <thead className="sticky top-0 bg-slate-900 text-white">
            <tr>
              <th className="px-3 py-2 font-semibold">نماد</th>
              <th className="px-3 py-2 font-semibold">وزن</th>
            </tr>
          </thead>
          <tbody>
            {weights.map((item) => (
              <tr
                key={item.symbol}
                className="border-b border-slate-100 last:border-b-0 odd:bg-white even:bg-slate-50"
              >
                <td className="px-3 py-2 font-bold text-slate-950">
                  {item.symbol}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  {formatPercent(item.weightDecimal)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </aside>
  )
}
