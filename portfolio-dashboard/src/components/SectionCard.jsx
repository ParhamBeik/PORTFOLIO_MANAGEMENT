export function SectionCard({ title, subtitle, children, className = '' }) {
  return (
    <section
      className={`rounded-lg border border-slate-800/10 bg-white p-5 shadow-[0_18px_50px_rgba(15,23,42,0.08)] lg:p-6 ${className}`}
    >
      <div className="mb-5">
        <h2 className="text-xl font-black text-slate-950">{title}</h2>
        {subtitle ? (
          <p className="mt-2 text-sm leading-6 text-slate-500">{subtitle}</p>
        ) : null}
      </div>
      {children}
    </section>
  )
}
