import { formatPercent, getWeightStatus } from '../utils/portfolio'

export function WeightsTable({ weights }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-right text-sm">
        <thead className="bg-slate-900 text-white">
          <tr>
            <th className="px-4 py-3 font-semibold">نماد</th>
            <th className="px-4 py-3 font-semibold">وزن</th>
            <th className="px-4 py-3 font-semibold">وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {weights.map((item) => (
            <tr
              key={item.symbol}
              className="border-b border-slate-100 last:border-b-0 odd:bg-white even:bg-slate-50"
            >
              <td className="px-4 py-3 font-bold text-slate-950">
                {item.symbol}
              </td>
              <td className="px-4 py-3 text-slate-700">
                {formatPercent(item.weight / 100)}
              </td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                  {getWeightStatus(item.weight)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
