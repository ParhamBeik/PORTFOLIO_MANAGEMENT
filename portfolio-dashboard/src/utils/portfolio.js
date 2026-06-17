export function formatNumber(value, options = {}) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'نامشخص'
  }

  return new Intl.NumberFormat('fa-IR', {
    maximumFractionDigits: 4,
    ...options,
  }).format(value)
}

export function formatDash(value, formatter = formatNumber) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—'
  }

  return formatter(value)
}

export function formatPercent(value, options = {}) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'نامشخص'
  }

  return new Intl.NumberFormat('fa-IR', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    ...options,
  }).format(value)
}

export function objectToWeightArray(weights = {}) {
  return Object.entries(weights).map(([symbol, weight]) => ({
    symbol,
    weight,
  }))
}

export function extractWeightsFromEfficientPortfolio(portfolio = {}) {
  const weightPrefix = 'weight_'

  return Object.entries(portfolio)
    .filter(([key]) => key.startsWith(weightPrefix))
    .map(([key, weight]) => ({
      symbol: key.slice(weightPrefix.length),
      weight,
    }))
}

export function normalizeWeightArray(weights = []) {
  return weights
    .filter(
      (item) =>
        item?.symbol &&
        typeof item.weight === 'number' &&
        Number.isFinite(item.weight),
    )
    .map((item) => ({
      ...item,
      weightDecimal: item.weight / 100,
    }))
}

export function getWeightStatus(weight) {
  if (Math.abs(weight - 30) < 0.001) {
    return 'در سقف مجاز'
  }

  if (Math.abs(weight) < 0.001) {
    return 'حذف‌شده از پرتفوی نهایی'
  }

  return 'فعال'
}

function readFirstNumber(source, keys) {
  for (const key of keys) {
    const value = source?.[key]

    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
  }

  return null
}

export function normalizeRiskReturnPoint(source = {}) {
  const risk = readFirstNumber(source, [
    'risk',
    'volatility',
    'std',
    'standard_deviation',
    'sigma',
  ])
  const expectedReturn = readFirstNumber(source, [
    'return',
    'expected_return',
    'mean_return',
    'target_return',
  ])
  const sharpe = readFirstNumber(source, [
    'sharpe',
    'sharpe_ratio',
    'sharpeRatio',
  ])

  if (risk === null || expectedReturn === null) {
    return null
  }

  return {
    iteration: source.iteration,
    label: source.label,
    portfolioId: source.portfolio_id,
    risk,
    return: expectedReturn,
    sharpe,
    source,
  }
}

export function getRandomPortfolioSamples(randomSamplesCloud) {
  if (Array.isArray(randomSamplesCloud)) {
    return randomSamplesCloud
  }

  if (Array.isArray(randomSamplesCloud?.samples)) {
    return randomSamplesCloud.samples
  }

  if (Array.isArray(randomSamplesCloud?.data)) {
    return randomSamplesCloud.data
  }

  return []
}

export function thinChartPoints(points, maxPoints = 2500) {
  if (points.length <= maxPoints) {
    return points
  }

  const step = Math.ceil(points.length / maxPoints)

  return points.filter((_, index) => index % step === 0)
}

function normalizeStrategyKey(name = '') {
  return name.replace(/[\u2010-\u2015]/g, '-')
}

const STRATEGY_LABELS = {
  'Equal Weight': 'وزن برابر',
  'Max Return Asset': 'شروع از سهم با بیشترین بازده',
  'Minimum Variance': 'شروع از کمترین واریانس',
  'Sharpe-Proportional': 'شروع متناسب با شارپ',
}

export function translateStrategyName(name) {
  return STRATEGY_LABELS[normalizeStrategyKey(name)] ?? name
}

export function getOptimizationStrategies(allOptimizationTrajectories = {}) {
  return Object.entries(allOptimizationTrajectories)
    .filter(([name]) => name !== '_metadata')
    .map(([name, result]) => ({
      name,
      label: translateStrategyName(name),
      success: Boolean(result?.success),
      finalSharpe: result?.sharpe,
      timeSeconds: result?.time_seconds,
      trajectory: Array.isArray(result?.trajectory) ? result.trajectory : [],
      iterations: Array.isArray(result?.trajectory)
        ? result.trajectory.length
        : 0,
    }))
}

export function getDisplaySharpe(point = {}) {
  if (typeof point.sharpe === 'number' && Number.isFinite(point.sharpe)) {
    return point.sharpe
  }

  if (
    typeof point.excess_return === 'number' &&
    typeof point.risk === 'number' &&
    point.risk !== 0
  ) {
    return point.excess_return / point.risk
  }

  const riskFreeRate =
    typeof point.risk_free_rate === 'number'
      ? point.risk_free_rate
      : point.risk_free_weekly

  if (
    typeof point.return === 'number' &&
    typeof riskFreeRate === 'number' &&
    typeof point.risk === 'number' &&
    point.risk !== 0
  ) {
    return (point.return - riskFreeRate) / point.risk
  }

  return null
}

export function createOptimalPortfolioSelection(optimalPortfolio = {}) {
  return {
    title: 'پرتفوی بهینه نهایی',
    portfolioId: null,
    risk: optimalPortfolio?.metrics?.volatility,
    return: optimalPortfolio?.metrics?.expected_return,
    sharpe: optimalPortfolio?.metrics?.sharpe_ratio,
    weights: objectToWeightArray(optimalPortfolio?.weights),
    sourceType: 'optimal',
  }
}

export function createEfficientPortfolioSelection(portfolio = {}) {
  return {
    title: 'پرتفوی انتخاب‌شده از مرز کارا',
    portfolioId: portfolio.portfolio_id,
    risk: portfolio.risk,
    return: portfolio.return,
    sharpe: portfolio.sharpe,
    weights: extractWeightsFromEfficientPortfolio(portfolio),
    sourceType: 'frontier',
  }
}
