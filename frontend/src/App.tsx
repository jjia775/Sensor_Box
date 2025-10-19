import { Navigate, useRoutes } from 'react-router-dom'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import DataViewerPage from './pages/DataViewer'
import DiseasesConfigPage from './pages/Diseases'
import HealthAdvisorPage from './pages/HealthAdvisor'

export default function App() {
  const element = useRoutes([
    { path: '/', element: <Login /> },
    { path: '/login', element: <Navigate to="/" replace /> },
    { path: '/register', element: <Register /> },
    { path: '/dashboard/:houseId', element: <Dashboard /> },
    { path: '/data-viewer', element: <DataViewerPage /> },
    { path: '/diseases', element: <DiseasesConfigPage /> },
    { path: '/health-advisor', element: <HealthAdvisorPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ])

  return element
}
