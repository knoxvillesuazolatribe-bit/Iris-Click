/**
 * Snapping onto the nearest button, the PC's TargetLock
 * (server/app/core/actions/target_snap.py), for page elements instead of
 * Windows controls. Webcam gaze error (~90 px) is larger than small buttons,
 * so the pointer locks onto a nearby control and switches only on clear intent.
 * Positions in CSS pixels; times in seconds.
 */

export const SNAP_RADIUS_PX = 140
const SWITCH_SECONDS = 0.15
const RELEASE_SECONDS = 0.35
const STICKY_RADIUS_FACTOR = 1.35
const SWITCH_HYSTERESIS_PX = 40

export interface Target {
  left: number
  top: number
  right: number
  bottom: number
  /** Opaque handle (the page element). */
  id: unknown
}

export const centreOf = (t: Target): [number, number] => [(t.left + t.right) / 2, (t.top + t.bottom) / 2]

export function distanceTo(t: Target, x: number, y: number): number {
  const dx = Math.max(t.left - x, 0, x - t.right)
  const dy = Math.max(t.top - y, 0, y - t.bottom)
  return Math.hypot(dx, dy)
}

/** The most plausible target within `radius`, or null. */
export function chooseTarget(x: number, y: number, targets: Target[], radius: number): Target | null {
  let best: { score: number; area: number; target: Target } | null = null
  for (const target of targets) {
    const edge = distanceTo(target, x, y)
    if (edge > radius) continue
    const [cx, cy] = centreOf(target)
    const area = (target.right - target.left) * (target.bottom - target.top)
    // Edge distance owns the whitespace; centre and area break ties between nested controls.
    const score = edge + Math.hypot(cx - x, cy - y) * 0.06 + area * 0.00001
    if (!best || score < best.score || (score === best.score && area < best.area)) best = { score, area, target }
  }
  return best?.target ?? null
}

export class TargetLock {
  active: Target | null = null
  private readonly radius: number
  private switchTo: Target | null = null
  private switchSince = 0
  private awaySince: number | null = null

  constructor(radius = SNAP_RADIUS_PX) {
    this.radius = radius
  }

  reset() {
    this.active = null
    this.switchTo = null
    this.awaySince = null
  }

  /** The locked target's centre (or the gaze point) and the target. */
  snap(x: number, y: number, targets: Target[], now: number): { x: number; y: number; target: Target | null } {
    const nearest = chooseTarget(x, y, targets, this.radius)
    const active = this.active ? targets.find((t) => t.id === this.active!.id) ?? null : null
    if (!active) {
      this.reset()
      this.active = nearest
    } else {
      this.active = active
      const activeDistance = distanceTo(active, x, y)
      let rival: Target | null = null
      if (nearest && nearest.id !== active.id) {
        const nearestDistance = distanceTo(nearest, x, y)
        if (nearestDistance === 0 || nearestDistance + SWITCH_HYSTERESIS_PX < activeDistance) rival = nearest
      }
      if (!rival) this.switchTo = null
      else if (rival.id !== this.switchTo?.id) {
        this.switchTo = rival
        this.switchSince = now
      }
      if (rival && now - this.switchSince >= SWITCH_SECONDS) {
        this.reset()
        this.active = rival
      } else if (activeDistance <= this.radius * STICKY_RADIUS_FACTOR || rival) {
        this.awaySince = null
      } else {
        if (this.awaySince === null) this.awaySince = now
        if (now - this.awaySince >= RELEASE_SECONDS) this.reset()
      }
    }
    if (!this.active) return { x, y, target: null }
    const [sx, sy] = centreOf(this.active)
    return { x: sx, y: sy, target: this.active }
  }
}
