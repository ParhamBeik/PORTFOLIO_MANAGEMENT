import {
  Dashboard,
  ErrorState,
  LoadingState,
} from './components/Dashboard'
import { usePortfolioData } from './hooks/usePortfolioData'

function App() {
  const { data, error, fileStatuses, loading } = usePortfolioData()

  if (loading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState error={error} fileStatuses={fileStatuses} />
  }

  return <Dashboard data={data} fileStatuses={fileStatuses} />
}

export default App
