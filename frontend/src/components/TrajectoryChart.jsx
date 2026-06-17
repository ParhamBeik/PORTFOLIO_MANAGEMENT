import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  formatDash,
  formatNumber,
  formatPercent,
  getDisplaySharpe,
  getOptimizationStrategies,
} from '../utils/portfolio'

function getDomain(values, paddingRatio = 0.12) {
  const finiteValues = values.filter(
    (value) => typeof value === 'number' && Number.isFinite(value),
  )

  if (!finiteValues.length) {
    return ['auto', 'auto']
  }

  const min = Math.min(...finiteValues)
  const max = Math.max(...finiteValues)
  const padding = (max - min) * paddingRatio || 0.002

  return [min - padding, max + padding]
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null
  }

  const point = payload[0]?.payload

  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 p-3 text-right text-xs shadow-lg">
      <p className="font-bold text-slate-950">تکرار {label}</p>
      {typeof point?.risk === 'number' ? (
        <p className="mt-2 text-slate-600">ریسک: {formatPercent(point.risk)}</p>
      ) : null}
      {typeof point?.return === 'number' ? (
        <p className="mt-1 text-slate-600">بازده: {formatPercent(point.return)}</p>
      ) : null}
      <p className="mt-1 text-slate-600">
        شارپ: {formatDash(point?.displaySharpe)}
      </p>
    </div>
  )
}

export function TrajectoryChart({ allOptimizationTrajectories }) {
  const strategies = useMemo(
    () => getOptimizationStrategies(allOptimizationTrajectories),
    [allOptimizationTrajectories],
  )
  const [selectedName, setSelectedName] = useState(strategies[0]?.name ?? '')
  const selectedStrategy =
    strategies.find((strategy) => strategy.name === selectedName) ??
    strategies[0]
  const trajectory = (selectedStrategy?.trajectory ?? []).map((item, index) => ({
    ...item,
    iteration: item.iteration ?? index + 1,
    displaySharpe: getDisplaySharpe(item),
  }))

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        {strategies.map((strategy) => (
          <button
            key={strategy.name}
            type="button"
            onClick={() => setSelectedName(strategy.name)}
            className={`rounded-full px-4 py-2 text-sm font-bold transition ${
              selectedStrategy?.name === strategy.name
                ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/20'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {strategy.label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-4">
          <h3 className="mb-4 font-black text-slate-950">
            روند نسبت شارپ در تکرارها
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trajectory} margin={{ top: 8, right: 8, bottom: 12, left: 4 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
                <XAxis
                  dataKey="iteration"
                  tick={{ fill: '#475569', fontSize: 12 }}
                  tickLine={false}
                />
                <YAxis
                  dataKey="displaySharpe"
                  domain={getDomain(trajectory.map((item) => item.displaySharpe))}
                  tick={{ fill: '#475569', fontSize: 12 }}
                  tickFormatter={(value) =>
                    formatNumber(value, { maximumFractionDigits: 3 })
                  }
                  tickLine={false}
                  width={64}
                />
                <Tooltip content={<ChartTooltip />} />
                <Line
                  dataKey="displaySharpe"
                  dot={{ r: 4, fill: '#059669', strokeWidth: 0 }}
                  isAnimationActive={false}
                  name="نسبت شارپ"
                  stroke="#059669"
                  strokeWidth={3}
                  type="monotone"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-4">
          <h3 className="mb-4 font-black text-slate-950">
            مسیر ریسک و بازده
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trajectory} margin={{ top: 8, right: 8, bottom: 12, left: 4 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
                <XAxis
                  dataKey="risk"
                  domain={getDomain(trajectory.map((item) => item.risk))}
                  tick={{ fill: '#475569', fontSize: 12 }}
                  tickFormatter={formatPercent}
                  tickLine={false}
                  type="number"
                />
                <YAxis
                  dataKey="return"
                  domain={getDomain(trajectory.map((item) => item.return))}
                  tick={{ fill: '#475569', fontSize: 12 }}
                  tickFormatter={formatPercent}
                  tickLine={false}
                  type="number"
                  width={64}
                />
                <Tooltip content={<ChartTooltip />} />
                <Line
                  dataKey="return"
                  dot={{ r: 4, fill: '#0f766e', strokeWidth: 0 }}
                  isAnimationActive={false}
                  name="مسیر"
                  stroke="#0f766e"
                  strokeWidth={3}
                  type="linear"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full border-collapse text-right text-sm">
          <thead className="bg-slate-900 text-white">
            <tr>
              <th className="px-4 py-3 font-semibold">تکرار</th>
              <th className="px-4 py-3 font-semibold">ریسک</th>
              <th className="px-4 py-3 font-semibold">بازده</th>
              <th className="px-4 py-3 font-semibold">شارپ</th>
            </tr>
          </thead>
          <tbody>
            {trajectory.map((item) => (
              <tr
                key={item.iteration}
                className="border-b border-slate-100 last:border-b-0 odd:bg-white even:bg-slate-50"
              >
                <td className="px-4 py-3 font-bold text-slate-950">
                  {formatNumber(item.iteration, { maximumFractionDigits: 0 })}
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {formatDash(item.risk, formatPercent)}
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {formatDash(item.return, formatPercent)}
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {formatDash(item.displaySharpe, (value) =>
                    formatNumber(value, { maximumFractionDigits: 4 }),
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
