import {
  formatDash,
  formatNumber,
  getOptimizationStrategies,
} from '../utils/portfolio'

export function StrategyComparisonTable({ allOptimizationTrajectories }) {
  const strategies = getOptimizationStrategies(allOptimizationTrajectories)

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-right text-sm">
        <thead className="bg-slate-900 text-white">
          <tr>
            <th className="px-4 py-3 font-semibold">استراتژی</th>
            <th className="px-4 py-3 font-semibold">موفقیت</th>
            <th className="px-4 py-3 font-semibold">شارپ نهایی</th>
            <th className="px-4 py-3 font-semibold">زمان اجرا</th>
            <th className="px-4 py-3 font-semibold">تعداد تکرار</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((strategy) => (
            <tr
              key={strategy.name}
              className="border-b border-slate-100 last:border-b-0 odd:bg-white even:bg-slate-50"
            >
              <td className="px-4 py-3">
                <p className="font-bold text-slate-950">{strategy.label}</p>
                <p className="mt-1 text-xs text-slate-400" dir="ltr">
                  {strategy.name}
                </p>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    strategy.success
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-rose-50 text-rose-700'
                  }`}
                >
                  {strategy.success ? 'موفق' : 'ناموفق'}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-700">
                {formatDash(strategy.finalSharpe, (value) =>
                  formatNumber(value, { maximumFractionDigits: 4 }),
                )}
              </td>
              <td className="px-4 py-3 text-slate-700">
                {formatDash(strategy.timeSeconds, (value) =>
                  `${formatNumber(value, { maximumFractionDigits: 5 })} ثانیه`,
                )}
              </td>
              <td className="px-4 py-3 text-slate-700">
                {formatNumber(strategy.iterations, { maximumFractionDigits: 0 })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
