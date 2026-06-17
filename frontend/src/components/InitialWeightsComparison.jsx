import {
  formatPercent,
  objectToWeightArray,
  translateStrategyName,
} from '../utils/portfolio'

export function InitialWeightsComparison({ optimizationInitializations }) {
  const initializations = Array.isArray(optimizationInitializations?.initializations)
    ? optimizationInitializations.initializations
    : []
  const symbols = objectToWeightArray(initializations[0]?.weights).map(
    (item) => item.symbol,
  )

  return (
    <div>
      <p className="mb-5 rounded-lg border border-emerald-500/20 bg-emerald-50 p-4 leading-8 text-emerald-950">
        برای اطمینان از پایداری جواب، الگوریتم از چند نقطه شروع متفاوت اجرا شده
        است. نزدیک بودن نسبت شارپ نهایی در این مسیرها نشان می‌دهد که مدل به یک
        جواب بهینه پایدار همگرا شده است.
      </p>

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-[760px] w-full border-collapse text-right text-sm">
          <thead className="bg-slate-900 text-white">
            <tr>
              <th className="px-4 py-3 font-semibold">نماد</th>
              {initializations.map((strategy) => (
                <th key={strategy.name} className="px-4 py-3 font-semibold">
                  {translateStrategyName(strategy.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map((symbol) => (
              <tr
                key={symbol}
                className="border-b border-slate-100 last:border-b-0 odd:bg-white even:bg-slate-50"
              >
                <td className="px-4 py-3 font-bold text-slate-950">{symbol}</td>
                {initializations.map((strategy) => (
                  <td key={`${strategy.name}-${symbol}`} className="px-4 py-3 text-slate-700">
                    {formatPercent((strategy.weights?.[symbol] ?? 0) / 100)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
