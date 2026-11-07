/**
 * Intentional wink detection, the PC's BlinkDetector
 * (server/app/core/detection/blink_detector.py):
 *  - an eye counts only after staying closed for `holdMs` (ordinary blinks are shorter);
 *  - a one-eyed wink needs the closing eye well below the open one, so an
 *    uneven ordinary blink never fires;
 *  - one event per closure, on reopening. Times are in milliseconds.
 */

export const CLOSED_FRACTION = 0.6
export const BOTH_CLOSED_EAR = 0.1
// Blink sensitivity steps 1 (less) to 5 (more), as on the PC.
export const BLINK_LEVELS = [0.14, 0.16, 0.18, 0.2, 0.22] as const

export type Closure = 'left' | 'right' | 'both'

export class WinkDetector {
  threshold: number
  private readonly holdMs: number
  private readonly cooldownMs: number
  private closedSince: number | null = null
  private kind: Closure | null = null
  private lastTrigger = -Infinity

  constructor(threshold = 0.18, holdMs = 350, cooldownMs = 700) {
    this.threshold = threshold
    this.holdMs = holdMs
    this.cooldownMs = cooldownMs
  }

  classify(leftEar: number, rightEar: number): Closure | null {
    if (Math.max(leftEar, rightEar) < BOTH_CLOSED_EAR) return 'both'
    if (leftEar < this.threshold && leftEar < CLOSED_FRACTION * rightEar) return 'left'
    if (rightEar < this.threshold && rightEar < CLOSED_FRACTION * leftEar) return 'right'
    return null
  }

  /** True while an eye is closing or closed (the pointer holds still then). */
  get closing(): boolean {
    return this.closedSince !== null
  }

  update(leftEar: number, rightEar: number, now: number): Closure | null {
    const kind = this.classify(leftEar, rightEar)
    if (kind !== null) {
      if (this.closedSince === null) {
        this.closedSince = now
        this.kind = kind
      } else if (kind === 'both') {
        // A wink that turns into a full blink is a blink.
        this.kind = 'both'
      }
      return null
    }
    if (this.closedSince === null) return null
    const duration = now - this.closedSince
    const closure = this.kind
    this.closedSince = null
    this.kind = null
    if (duration < this.holdMs || now - this.lastTrigger < this.cooldownMs) return null
    this.lastTrigger = now
    return closure
  }

  reset() {
    this.closedSince = null
    this.kind = null
  }
}
