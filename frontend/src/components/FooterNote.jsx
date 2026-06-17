import { formatNumber } from '../utils/portfolio'

export function FooterNote({ optimizationTrajectory }) {
  const selectedTrajectoryLength = Array.isArray(optimizationTrajectory?.trajectory)
    ? optimizationTrajectory.trajectory.length
    : 0

  return (
    <footer className="rounded-lg border border-slate-800/10 bg-slate-950 p-6 text-slate-200 shadow-[0_18px_50px_rgba(15,23,42,0.12)]">
      <p className="text-base font-bold text-white">
        یادداشت پایانی ارائه
      </p>
      <p className="mt-3 leading-8 text-slate-300">
        همه محاسبات بهینه‌سازی خارج از React انجام شده‌اند و این داشبورد فقط
        خروجی‌های ذخیره‌شده در فایل‌های محلی را نمایش می‌دهد. فایل
        optimization_trajectory.json نیز به عنوان مسیر منتخب مستقل بارگذاری شده
        و شامل {formatNumber(selectedTrajectoryLength, { maximumFractionDigits: 0 })}{' '}
        گام است.
      </p>
    </footer>
  )
}
