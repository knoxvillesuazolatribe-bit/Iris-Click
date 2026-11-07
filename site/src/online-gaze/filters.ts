/**
 * One Euro filter (Casiez, Roussel & Vogel, CHI 2012), as on the PC
 * (server/app/core/gaze/smoothing.py): smooths hard while the gaze rests and
 * relaxes during fast, intentional eye movement. Times are in seconds.
 */

const alpha = (freq: number, cutoff: number) => {
  const te = 1 / freq
  const tau = 1 / (2 * Math.PI * cutoff)
  return 1 / (1 + tau / te)
}

export class OneEuroFilter {
  private x: number | null = null
  private dx = 0
  private lastTime: number | null = null
  private freq: number
  mincutoff: number
  private readonly beta: number
  private readonly dcutoff: number

  constructor(freq = 30, mincutoff = 0.8, beta = 0.01, dcutoff = 1) {
    this.freq = freq
    this.mincutoff = mincutoff
    this.beta = beta
    this.dcutoff = dcutoff
  }

  filter(value: number, time: number): number {
    if (this.lastTime !== null) {
      const dt = time - this.lastTime
      if (dt <= 0) return this.x ?? value
      this.freq = 1 / dt
    }
    this.lastTime = time
    if (this.x === null) {
      this.x = value
      return value
    }
    // Velocity relative to the previous filtered value (reference algorithm).
    const a = alpha(this.freq, this.dcutoff)
    this.dx = a * ((value - this.x) * this.freq) + (1 - a) * this.dx
    const cutoff = this.mincutoff + this.beta * Math.abs(this.dx)
    const b = alpha(this.freq, cutoff)
    this.x = b * value + (1 - b) * this.x
    return this.x
  }

  reset() {
    this.x = null
    this.dx = 0
    this.lastTime = null
  }
}

export class OneEuroFilter2D {
  private readonly fx: OneEuroFilter
  private readonly fy: OneEuroFilter

  constructor(mincutoff = 0.8, beta = 0.01) {
    this.fx = new OneEuroFilter(30, mincutoff, beta)
    this.fy = new OneEuroFilter(30, mincutoff, beta)
  }

  filter(x: number, y: number, time: number): [number, number] {
    return [this.fx.filter(x, time), this.fy.filter(y, time)]
  }

  reset() {
    this.fx.reset()
    this.fy.reset()
  }
}

/**
 * The user's Smoothing setting as One Euro minimum cut-off (Hz):
 * lower is steadier but follows a little slower.
 */
export const SMOOTHING_CUTOFF = { low: 1.6, medium: 0.8, high: 0.4 } as const
