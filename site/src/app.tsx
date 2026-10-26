import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { CalibrationPage } from '@/pages/calibration-page'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/calibration" element={<CalibrationPage />} />
        <Route path="*" element={<Navigate to="/calibration" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
