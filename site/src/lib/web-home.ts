/**
 * One home, on the web: when IrisClick Desktop says calibration finished, or its control bar's
 * Home is pressed, the open IrisClick page shows the Home Suite. IrisClick Desktop itself has no
 * home screen; it only calibrates and moves the cursor.
 */

/** Pages that already decide what comes after calibration (Home Suite countdown, account setup). */
const OWN_NEXT_STEP = ['/calibration', '/user/add']

export interface DesktopNotice {
  type?: unknown
  status?: unknown
}

/** True when ``notice`` should take this page to /home. */
export function goesHome(notice: DesktopNotice, pathname: string, signedIn: boolean): boolean {
  if (!signedIn || pathname === '/home') return false
  if (notice.type === 'app.go_home') return true
  if (notice.type === 'calibration.result' && notice.status === 'success') {
    return !OWN_NEXT_STEP.some((path) => pathname === path || pathname.startsWith(`${path}/`))
  }
  return false
}
