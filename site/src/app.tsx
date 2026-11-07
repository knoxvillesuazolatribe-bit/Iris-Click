import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { OnlineAccessGate } from '@/components/online-access-gate'
import { RequireRole } from '@/components/require-role'
import { ONLINE_COPY } from '@/lib/online-copy'
import { useAppName } from '@/lib/use-app-name'
import { AdminLoginPage } from '@/pages/admin-login-page'
import { AdminLogsPage } from '@/pages/admin-logs-page'
import { AdminPage } from '@/pages/admin-page'
import { AdminReportPage, AdminReportsPage } from '@/pages/admin-reports-pages'
import { AdminAccessibilityPage, AdminSettingsPage, AdminSystemPage } from '@/pages/admin-settings-pages'
import { AdminWordFilterPage } from '@/pages/admin-word-filter-page'
import { AdminUserPage } from '@/pages/admin-user-page'
import { AdminUsersPage } from '@/pages/admin-users-page'
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

// Online copy only: browser eye tracking, loaded on demand so the PC build never includes it.
const GazeLayer = lazy(() => import('@/online-gaze/gaze-layer').then((m) => ({ default: m.GazeLayer })))
const OnlineCalibrationPage = lazy(() =>
  import('@/online-gaze/online-calibration-page').then((m) => ({ default: m.OnlineCalibrationPage })))
const OnlineTrackingPage = lazy(() =>
  import('@/online-gaze/online-tracking-page').then((m) => ({ default: m.OnlineTrackingPage })))

// Online copy hook: the access code comes first (on the PC build the gate renders App as before).
export function App() {
  return (
    <OnlineAccessGate>
      <Pages />
    </OnlineAccessGate>
  )
}

function Pages() {
  useAppName() // browser tab title = the app name the admin set, on every page
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginSelectionPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/user/select" element={<UserSelectPage />} />
        <Route path="/home" element={<RequireRole role="assistive_user"><HomePage /></RequireRole>} />
        {/* Online copy hook: eye tracking runs in the browser there. */}
        <Route path="/tracking" element={<RequireRole role="assistive_user">{ONLINE_COPY ? <Suspense fallback={null}><OnlineTrackingPage /></Suspense> : <TrackingPage />}</RequireRole>} />
        <Route path="/voice" element={<RequireRole role="assistive_user"><VoicePage /></RequireRole>} />
        <Route path="/sos" element={<RequireRole role="assistive_user"><SosPage /></RequireRole>} />
        <Route path="/sos/confirm" element={<RequireRole role="assistive_user"><SosConfirmPage /></RequireRole>} />
        <Route path="/sos/sent" element={<RequireRole role="assistive_user"><SosSentPage /></RequireRole>} />
        <Route path="/sos/contacts" element={<RequireRole role="assistive_user"><SosContactsPage /></RequireRole>} />
        <Route path="/settings" element={<RequireRole role="assistive_user"><SettingsPage /></RequireRole>} />
        <Route path="/admin" element={<RequireRole role="admin"><AdminPage /></RequireRole>} />
        <Route path="/admin/users" element={<RequireRole role="admin"><AdminUsersPage /></RequireRole>} />
        <Route path="/admin/users/:id" element={<RequireRole role="admin"><AdminUserPage /></RequireRole>} />
        <Route path="/admin/settings" element={<RequireRole role="admin"><AdminSettingsPage /></RequireRole>} />
        <Route path="/admin/settings/accessibility" element={<RequireRole role="admin"><AdminAccessibilityPage /></RequireRole>} />
        <Route path="/admin/settings/system" element={<RequireRole role="admin"><AdminSystemPage /></RequireRole>} />
        <Route path="/admin/settings/word-filter" element={<RequireRole role="admin"><AdminWordFilterPage /></RequireRole>} />
        <Route path="/admin/logs" element={<RequireRole role="admin"><AdminLogsPage /></RequireRole>} />
        <Route path="/admin/reports" element={<RequireRole role="admin"><AdminReportsPage /></RequireRole>} />
        <Route path="/admin/reports/:type" element={<RequireRole role="admin"><AdminReportPage /></RequireRole>} />
        {/* Online copy hook: the browser's own calibration instead of the PC's. */}
        <Route path="/calibration" element={ONLINE_COPY
          ? <RequireRole role="assistive_user"><Suspense fallback={null}><OnlineCalibrationPage /></Suspense></RequireRole>
          : <CalibrationPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {ONLINE_COPY && <Suspense fallback={null}><GazeLayer /></Suspense>}
    </BrowserRouter>
  )
}
