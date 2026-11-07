/**
 * Dwell click and edge scroll, the PC's DwellClicker
 * (server/app/core/actions/dwell_click.py) and EdgeScroller
 * (server/app/workers/edge_scroll.py). Times in milliseconds, CSS pixels.
 */

export class DwellClicker {
  private anchor: [number, number] | null = null
  private start = 0
  private armed = true
  private lastClick = -Infinity
  dwellMs: number
  private readonly radiusPx: number
  private readonly cooldownMs: number

  constructor(dwellMs = 700, radiusPx = 45, cooldownMs = 500) {
    this.dwellMs = dwellMs
    this.radiusPx = radiusPx
    this.cooldownMs = cooldownMs
  }

  reset() {
    this.anchor = null
    this.armed = true
  }

  /** Completion 0..1 for the progress ring. */
  progress(now: number): number {
    if (!this.anchor || !this.armed) return 0
    return Math.min(1, (now - this.start) / this.dwellMs)
  }

  /** True exactly when a click should fire. */
  update(x: number, y: number, now: number): boolean {
    if (!this.anchor || Math.hypot(x - this.anchor[0], y - this.anchor[1]) > this.radiusPx) {
      this.anchor = [x, y]
      this.start = now
      this.armed = true
      return false
    }
    if (!this.armed || now - this.start < this.dwellMs || now - this.lastClick < this.cooldownMs) return false
    this.armed = false
    this.lastClick = now
    return true
  }
}

export const EDGE_BAND_FRACTION = 0.08
const SCROLL_EVERY_MS = 200
const GAP_RESET_MS = 300

export type ScrollDirection = 'up' | 'down'

export class EdgeScroller {
  private zone: ScrollDirection | null = null
  private nextScroll = 0
  private lastUpdate: number | null = null
  dwellMs: number

  constructor(dwellMs = 700) {
    this.dwellMs = dwellMs
  }

  /** Feeds the shown pointer position; returns the direction to scroll now, if any. */
  update(y: number, viewportHeight: number, now: number): ScrollDirection | null {
    if (this.lastUpdate !== null && now - this.lastUpdate > GAP_RESET_MS) this.zone = null
    this.lastUpdate = now
    const band = Math.max(1, Math.round(viewportHeight * EDGE_BAND_FRACTION))
    const zone: ScrollDirection | null = y < band ? 'up' : y >= viewportHeight - band ? 'down' : null
    if (zone !== this.zone) {
      this.zone = zone
      this.nextScroll = now + this.dwellMs
    }
    if (zone === null || now < this.nextScroll) return null
    this.nextScroll = now + SCROLL_EVERY_MS
    return zone
  }
}
