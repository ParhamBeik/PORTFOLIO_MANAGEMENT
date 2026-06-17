export function MetricCard({ label, value, helper }) {
  return (
    <article className="rounded-lg border border-slate-800/10 bg-white p-5 shadow-[0_16px_40px_rgba(15,23,42,0.08)]">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <strong className="mt-3 block text-2xl font-black text-slate-950 lg:text-3xl">
        {value}
      </strong>
      {helper ? <p className="mt-2 text-xs text-slate-400">{helper}</p> : null}
    </article>
  )
}
