import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Dev-only isolated preview of the 3D drone model; dead code in production builds.
const DronePreviewPage = import.meta.env.DEV
  ? lazy(() => import('./features/drone3d/DronePreviewPage'))
  : null
const showDronePreview =
  DronePreviewPage !== null &&
  new URLSearchParams(window.location.search).get('preview') === 'drone3d'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {showDronePreview ? (
      <Suspense fallback={null}>
        <DronePreviewPage />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
