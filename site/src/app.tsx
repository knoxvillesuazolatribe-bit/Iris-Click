import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { RequireRole } from '@/components/require-role'
import { AdminLoginPage } from '@/pages/admin-login-page'
import { AdminPage } from '@/pages/admin-page'
import { CalibrationPage } from '@/pages/calibration-page'
import { HomePage } from '@/pages/home-page'
import { LoginSelectionPage } from '@/pages/login-selection-page'
import { TrackingPage } from '@/pages/tracking-page'
import { UserSelectPage } from '@/pages/user-select-page'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginSelectionPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/user/select" element={<UserSelectPage />} />
        <Route path="/home" element={<RequireRole role="assistive_user"><HomePage /></RequireRole>} />
        <Route path="/tracking" element={<RequireRole role="assistive_user"><TrackingPage /></RequireRole>} />
        <Route path="/admin" element={<RequireRole role="admin"><AdminPage /></RequireRole>} />
        <Route path="/calibration" element={<CalibrationPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
