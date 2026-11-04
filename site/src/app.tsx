import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { RequireRole } from '@/components/require-role'
import { AdminLoginPage } from '@/pages/admin-login-page'
import { AdminPage } from '@/pages/admin-page'
import { CalibrationPage } from '@/pages/calibration-page'
import { HomePage } from '@/pages/home-page'
import { LoginSelectionPage } from '@/pages/login-selection-page'
import { SettingsPage } from '@/pages/settings-page'
import { SosConfirmPage } from '@/pages/sos-confirm-page'
import { SosContactsPage } from '@/pages/sos-contacts-page'
import { SosPage } from '@/pages/sos-page'
import { SosSentPage } from '@/pages/sos-sent-page'
import { TrackingPage } from '@/pages/tracking-page'
import { UserSelectPage } from '@/pages/user-select-page'
import { VoicePage } from '@/pages/voice-page'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginSelectionPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/user/select" element={<UserSelectPage />} />
        <Route path="/home" element={<RequireRole role="assistive_user"><HomePage /></RequireRole>} />
        <Route path="/tracking" element={<RequireRole role="assistive_user"><TrackingPage /></RequireRole>} />
        <Route path="/voice" element={<RequireRole role="assistive_user"><VoicePage /></RequireRole>} />
        <Route path="/sos" element={<RequireRole role="assistive_user"><SosPage /></RequireRole>} />
        <Route path="/sos/confirm" element={<RequireRole role="assistive_user"><SosConfirmPage /></RequireRole>} />
        <Route path="/sos/sent" element={<RequireRole role="assistive_user"><SosSentPage /></RequireRole>} />
        <Route path="/sos/contacts" element={<RequireRole role="assistive_user"><SosContactsPage /></RequireRole>} />
        <Route path="/settings" element={<RequireRole role="assistive_user"><SettingsPage /></RequireRole>} />
        <Route path="/admin" element={<RequireRole role="admin"><AdminPage /></RequireRole>} />
        <Route path="/calibration" element={<CalibrationPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
