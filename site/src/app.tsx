import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { OnlineAccessGate } from '@/components/online-access-gate'
import { DesktopGate } from '@/components/desktop-gate'
import { CalibrationSurfaceSwitch } from '@/components/calibration-surface-switch'
import { DesktopDownloadPage } from '@/pages/desktop-download-page'
import { ApproveComputerPage } from '@/pages/approve-computer-page'
import { DesktopTrackingPage } from '@/pages/desktop-tracking-page'
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
import { AccountsPage } from '@/pages/accounts-page'
import { SigninModeSwitch } from '@/components/signin-mode-switch'
import { AddAccountPage } from '@/pages/add-account-page'
import { IdleSignOut } from '@/components/idle-signout'
import { AddressPage } from '@/pages/address-page'
import { VoicePage } from '@/pages/voice-page'

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
      <IdleSignOut>
      <Routes>
        <Route path="/" element={<LoginSelectionPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/user/select" element={<SigninModeSwitch legacy={<UserSelectPage />} deviceAccounts={<AccountsPage />} />} />
        <Route path="/user/add" element={<AddAccountPage />} />
        <Route path="/home" element={<RequireRole role="assistive_user"><HomePage /></RequireRole>} />
        <Route path="/tracking" element={<RequireRole role="assistive_user">{ONLINE_COPY
          ? <DesktopGate><DesktopTrackingPage /></DesktopGate> : <TrackingPage />}</RequireRole>} />
        {ONLINE_COPY && <Route path="/desktop" element={<DesktopDownloadPage />} />}
        {ONLINE_COPY && <Route path="/approve" element={<ApproveComputerPage />} />}
        <Route path="/voice" element={<RequireRole role="assistive_user"><VoicePage /></RequireRole>} />
        <Route path="/sos" element={<RequireRole role="assistive_user"><SosPage /></RequireRole>} />
        <Route path="/sos/confirm" element={<RequireRole role="assistive_user"><SosConfirmPage /></RequireRole>} />
        <Route path="/sos/sent" element={<RequireRole role="assistive_user"><SosSentPage /></RequireRole>} />
        <Route path="/sos/contacts" element={<RequireRole role="assistive_user"><SosContactsPage /></RequireRole>} />
        <Route path="/sos/address" element={<RequireRole role="assistive_user"><AddressPage /></RequireRole>} />
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
        {/* Hybrid hook: the hosted site uses the EXISTING calibration page, through IrisClick Desktop. */}
        {/* Desktop calibration hook: IrisClick Desktop chooses web (default: the page above) or its own window. */}
        <Route path="/calibration" element={ONLINE_COPY
          ? <DesktopGate><CalibrationSurfaceSwitch web={<CalibrationPage />} /></DesktopGate>
          : <CalibrationSurfaceSwitch web={<CalibrationPage />} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </IdleSignOut>
    </BrowserRouter>
  )
}
