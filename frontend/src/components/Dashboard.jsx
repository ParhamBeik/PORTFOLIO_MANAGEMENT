import { useState } from 'react'
import { EfficientFrontierInteractive } from './EfficientFrontierInteractive'
import { ImageGallery } from './ImageGallery'
import { InitialWeightsComparison } from './InitialWeightsComparison'
import { MetricCard } from './MetricCard'
import { ModelExplanation } from './ModelExplanation'
import { PortfolioWeightsChart } from './PortfolioWeightsChart'
import { SectionCard } from './SectionCard'
import { SelectedPortfolioPanel } from './SelectedPortfolioPanel'
import { StrategyComparisonTable } from './StrategyComparisonTable'
import { TrajectoryChart } from './TrajectoryChart'
import { WeightsTable } from './WeightsTable'
import {
  createOptimalPortfolioSelection,
  formatNumber,
  formatPercent,
  objectToWeightArray,
} from '../utils/portfolio'

const navLinks = [
  { href: '#summary', label: 'خلاصه نتایج' },
  { href: '#portfolio', label: 'پرتفوی بهینه' },
  { href: '#frontier', label: 'مرز کارا' },
  { href: '#optimization', label: 'مسیر بهینه‌سازی' },
  { href: '#gallery', label: 'نمودارهای خروجی' },
]

export function LoadingState() {
  return (
    <main
      dir="rtl"
      className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white"
    >
      <section className="w-full max-w-xl rounded-lg border border-white/10 bg-white/10 p-6 text-center shadow-2xl">
        <p className="text-lg font-bold">در حال بارگذاری داده‌های پرتفوی...</p>
        <p className="mt-2 text-sm text-slate-300">
          داده‌ها از فایل‌های محلی داخل public/data خوانده می‌شوند.
        </p>
      </section>
    </main>
  )
}

export function ErrorState({ error }) {
  return (
    <main
      dir="rtl"
      className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white"
    >
      <section className="w-full max-w-2xl rounded-lg border border-rose-400/30 bg-rose-950/40 p-6 shadow-2xl">
        <h1 className="text-2xl font-black text-rose-100">
          خطا در بارگذاری فایل‌های محلی
        </h1>
        <p className="mt-3 leading-7 text-rose-50">{error}</p>
      </section>
    </main>
  )
}

export function Dashboard({ data }) {
  const optimalPortfolio = data.optimalPortfolio ?? {}
  const metrics = optimalPortfolio.metrics ?? {}
  const weights = objectToWeightArray(optimalPortfolio.weights)
  const [selectedPortfolio, setSelectedPortfolio] = useState(() =>
    createOptimalPortfolioSelection(optimalPortfolio),
  )

  return (
    <main
      dir="rtl"
      className="min-h-screen bg-slate-100 text-right text-slate-900"
    >
      <section className="bg-slate-950 px-4 py-10 text-white sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-4xl">
            <p className="text-sm font-bold text-emerald-300">
              نتایج بهینه‌سازی سهام بورس تهران
            </p>
            <h1 className="mt-4 text-4xl font-black leading-tight sm:text-5xl lg:text-6xl">
              داشبورد بهینه‌سازی پرتفوی سهام
            </h1>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              نمایش نتایج بیشینه‌سازی نسبت شارپ برای پرتفوی منتخب بورس تهران
            </p>
          </div>
        </div>
      </section>

      <nav className="sticky top-0 z-20 border-b border-slate-800/10 bg-white/90 px-4 py-3 shadow-sm backdrop-blur sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto text-sm font-bold text-slate-700">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="whitespace-nowrap rounded-full px-4 py-2 transition hover:bg-emerald-50 hover:text-emerald-700"
            >
              {link.label}
            </a>
          ))}
        </div>
      </nav>

      <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <section
          id="summary"
          className="scroll-mt-24 grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
        >
          <MetricCard
            label="نسبت شارپ"
            value={formatNumber(metrics.sharpe_ratio, {
              maximumFractionDigits: 3,
            })}
          />
          <MetricCard
            label="بازده مورد انتظار هفتگی"
            value={formatPercent(metrics.expected_return)}
          />
          <MetricCard
            label="نوسان هفتگی"
            value={formatPercent(metrics.volatility)}
          />
          <MetricCard
            label="بازده سالانه‌شده"
            value={formatPercent(metrics.annualized_return)}
          />
          <MetricCard
            label="نوسان سالانه‌شده"
            value={formatPercent(metrics.annualized_volatility)}
          />
        </section>

        <section
          id="portfolio"
          className="scroll-mt-24 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]"
        >
          <SectionCard
            title="وزن‌های پرتفوی بهینه"
            subtitle="ترکیب نهایی دارایی‌ها پس از اعمال محدودیت سقف وزن، ممنوعیت فروش استقراضی و مجموع وزن ۱۰۰٪."
          >
            <PortfolioWeightsChart weights={weights} />
          </SectionCard>

          <SectionCard title="جدول وزن‌ها و وضعیت نمادها">
            <WeightsTable weights={weights} />
          </SectionCard>
        </section>

        <section id="frontier" className="scroll-mt-24">
          <SectionCard
            title="مرز کارا و پرتفوی با بهترین نسبت شارپ"
            subtitle="روی نقاط مرز کارا حرکت کنید یا کلیک کنید تا وزن‌های همان پرتفوی در پنل کناری نمایش داده شود."
          >
            <div className="grid gap-6 xl:grid-cols-[0.38fr_0.62fr]">
              <SelectedPortfolioPanel selectedPortfolio={selectedPortfolio} />
              <EfficientFrontierInteractive
                efficientFrontier={data.efficientFrontier}
                optimalPortfolio={optimalPortfolio}
                randomSamplesCloud={data.randomSamplesCloud}
                selectedPortfolio={selectedPortfolio}
                onSelectPortfolio={setSelectedPortfolio}
              />
            </div>
          </SectionCard>
        </section>

        <section className="scroll-mt-24">
          <ModelExplanation />
        </section>

        <section id="optimization" className="scroll-mt-24 space-y-8">
          <SectionCard
            title="مقایسه استراتژی‌های شروع بهینه‌سازی"
            subtitle="الگوریتم از چند نقطه شروع متفاوت اجرا شده تا پایداری جواب نهایی بررسی شود."
          >
            <StrategyComparisonTable
              allOptimizationTrajectories={data.allOptimizationTrajectories}
            />
          </SectionCard>

          <SectionCard
            title="نمایش مسیر بهینه‌سازی"
            subtitle="برای هر استراتژی، روند نسبت شارپ و مسیر حرکت در فضای ریسک و بازده نمایش داده شده است."
          >
            <TrajectoryChart
              allOptimizationTrajectories={data.allOptimizationTrajectories}
            />
          </SectionCard>

          <SectionCard
            title="مقایسه وزن‌های اولیه"
            subtitle="وزن‌های آغازین چهار استراتژی، پیش از همگرایی به پرتفوی نهایی."
          >
            <InitialWeightsComparison
              optimizationInitializations={data.optimizationInitializations}
            />
          </SectionCard>
        </section>

        <section id="gallery" className="scroll-mt-24">
          <SectionCard
            title="نمودارهای خروجی محاسبات"
            subtitle="تصاویر تولیدشده در مرحله تحلیل پایتون برای استفاده در ارائه کلاسی."
          >
            <ImageGallery />
          </SectionCard>
        </section>
      </div>
    </main>
  )
}
