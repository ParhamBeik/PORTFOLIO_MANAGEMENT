import { useEffect, useMemo, useState } from 'react'

const DATA_FILES = {
  optimalPortfolio: {
    label: 'پرتفوی بهینه',
    path: '/data/optimal_portfolio.json',
  },
  efficientFrontier: {
    label: 'مرز کارا',
    path: '/data/efficient_frontier.json',
  },
  randomSamplesCloud: {
    label: 'نمونه‌های تصادفی',
    path: '/data/random_samples_cloud.json',
  },
  allOptimizationTrajectories: {
    label: 'همه مسیرهای بهینه‌سازی',
    path: '/data/all_optimization_trajectories.json',
  },
  optimizationInitializations: {
    label: 'مقداردهی‌های اولیه',
    path: '/data/optimization_initializations.json',
  },
  optimizationTrajectory: {
    label: 'مسیر بهینه‌سازی منتخب',
    path: '/data/optimization_trajectory.json',
  },
}

function createFileStatuses(status) {
  return Object.fromEntries(
    Object.entries(DATA_FILES).map(([key, config]) => [
      key,
      {
        ...config,
        status,
        error: null,
      },
    ]),
  )
}

async function fetchJsonFile([key, config], signal) {
  const response = await fetch(config.path, { signal })

  if (!response.ok) {
    throw new Error(`${config.path}: ${response.status} ${response.statusText}`)
  }

  return {
    key,
    data: await response.json(),
  }
}

export function usePortfolioData() {
  const [state, setState] = useState({
    data: {},
    error: null,
    fileStatuses: createFileStatuses('loading'),
    loading: true,
  })

  useEffect(() => {
    const controller = new AbortController()

    Promise.allSettled(
      Object.entries(DATA_FILES).map((entry) =>
        fetchJsonFile(entry, controller.signal),
      ),
    ).then((results) => {
      if (controller.signal.aborted) {
        return
      }

      const data = {}
      const fileStatuses = {}
      const errors = []
      const entries = Object.entries(DATA_FILES)

      results.forEach((result, index) => {
        const [key, config] = entries[index]

        if (result.status === 'fulfilled') {
          data[result.value.key] = result.value.data
          fileStatuses[key] = {
            ...config,
            status: 'success',
            error: null,
          }
          return
        }

        const message = result.reason?.message ?? 'خطای ناشناخته'
        errors.push(`${config.label}: ${message}`)
        fileStatuses[key] = {
          ...config,
          status: 'error',
          error: message,
        }
      })

      setState({
        data,
        error: errors.length ? errors.join(' | ') : null,
        fileStatuses,
        loading: false,
      })
    })

    return () => {
      controller.abort()
    }
  }, [])

  return useMemo(
    () => ({
      ...state,
      files: DATA_FILES,
    }),
    [state],
  )
}
