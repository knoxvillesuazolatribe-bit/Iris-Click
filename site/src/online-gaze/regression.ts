/**
 * Gaze-to-screen mapping, the PC's eye-only CalibrationModel
 * (server/app/core/gaze/screen_mapper.py) for the eye-midpoint source:
 * ridge-regularised quadratic regression from (ex, ey) to screen fractions,
 * per-dot weighting, one robust refit that drops saccade frames, and the
 * capped edge stretch that undoes the pull toward the centre.
 */

export const MODEL_SOURCE = 'web_eye_midpoint_v1'
export const MODEL_VERSION = 1

const RIDGE_LAMBDA = 0.05
// Floors for the non-bias columns: ex, ey, ex², ey², ex·ey (PC SCALE_FLOORS).
const SCALE_FLOORS = [0.025, 0.025, 0.025, 0.025, 0.02]
const MIN_SAMPLES = 12
const MIN_GROUP_INLIERS = 8
const OUTLIER_MAD_MULTIPLIER = 3.5
const OUTLIER_NORMALIZED_FLOOR = 0.012
const MAX_EDGE_STRETCH = 1.5
const MIN_STRETCH_DOTS = 5

// Accepted up to the first limit; accepted with a low-accuracy note up to the
// second (large buttons still work); rejected above it. Screen fractions.
export const MAX_FIT_ERROR_FRACTION = 0.06
export const MAX_LOW_ACCURACY_FRACTION = 0.1

export type Vec2 = [number, number]

export interface Sample {
  /** (ex, ey) eye features. */
  f: Vec2
  /** Dot position as screen fractions (0..1). */
  t: Vec2
}

export interface GazeModel {
  source: typeof MODEL_SOURCE
  version: number
  mean: number[]
  scale: number[]
  coefX: number[]
  coefY: number[]
  /** offset x, gain x, offset y, gain y */
  stretch: [number, number, number, number]
}

const expand = ([ex, ey]: Vec2): number[] => [1, ex, ey, ex * ex, ey * ey, ex * ey]
const key = (t: Vec2) => `${t[0].toFixed(3)},${t[1].toFixed(3)}`

export function median(values: number[]): number {
  if (values.length === 0) return NaN
  const s = [...values].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** Solves A x = b (small dense system) by Gaussian elimination with pivoting. */
export function solve(a: number[][], b: number[]): number[] {
  const n = b.length
  const m = a.map((row, i) => [...row, b[i]])
  for (let col = 0; col < n; col++) {
    let pivot = col
    for (let r = col + 1; r < n; r++) if (Math.abs(m[r][col]) > Math.abs(m[pivot][col])) pivot = r
    if (Math.abs(m[pivot][col]) < 1e-12) throw new Error('The calibration model did not fit.')
    ;[m[col], m[pivot]] = [m[pivot], m[col]]
    for (let r = 0; r < n; r++) {
      if (r === col) continue
      const factor = m[r][col] / m[col][col]
      for (let c = col; c <= n; c++) m[r][c] -= factor * m[col][c]
    }
  }
  return m.map((row, i) => row[n] / row[i])
}

function normalise(row: number[], mean: number[], scale: number[]): number[] {
  return row.map((v, i) => (i === 0 ? v : (v - mean[i - 1]) / scale[i - 1]))
}

const dotProduct = (a: number[], b: number[]) => a.reduce((s, v, i) => s + v * b[i], 0)

interface Fit {
  mean: number[]
  scale: number[]
  coefX: number[]
  coefY: number[]
}

function fitRows(raw: number[][], targets: Vec2[], weights: number[]): Fit {
  const cols = raw[0].length
  const weightSum = weights.reduce((s, w) => s + w, 0)
  const mean: number[] = []
  const scale: number[] = []
  for (let c = 1; c < cols; c++) {
    const m = raw.reduce((s, row, i) => s + row[c] * weights[i], 0) / weightSum
    const v = raw.reduce((s, row, i) => s + (row[c] - m) ** 2 * weights[i], 0) / weightSum
    mean.push(m)
    scale.push(Math.max(Math.sqrt(v), SCALE_FLOORS[c - 1]))
  }
  const rows = raw.map((row) => normalise(row, mean, scale))
  const sqrtW = weights.map((w) => Math.sqrt(w * (weights.length / weightSum)))
  const ata = Array.from({ length: cols }, (_, i) =>
    Array.from({ length: cols }, (_, j) =>
      rows.reduce((s, row, k) => s + row[i] * row[j] * sqrtW[k] ** 2, 0) + (i === j && i > 0 ? RIDGE_LAMBDA : 0)))
  const atb = (axis: 0 | 1) =>
    Array.from({ length: cols }, (_, i) => rows.reduce((s, row, k) => s + row[i] * targets[k][axis] * sqrtW[k] ** 2, 0))
  return { mean, scale, coefX: solve(ata, atb(0)), coefY: solve(ata, atb(1)) }
}

function predictRaw(fit: Fit, raw: number[]): Vec2 {
  const row = normalise(raw, fit.mean, fit.scale)
  return [dotProduct(row, fit.coefX), dotProduct(row, fit.coefY)]
}

function linearSlope(x: number[], y: number[]): number {
  const mx = x.reduce((s, v) => s + v, 0) / x.length
  const my = y.reduce((s, v) => s + v, 0) / y.length
  const sxx = x.reduce((s, v) => s + (v - mx) ** 2, 0)
  return sxx === 0 ? 1 : x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0) / sxx
}

function edgeStretch(predicted: Vec2[], targets: Vec2[]): GazeModel['stretch'] {
  const groups = new Map<string, { t: Vec2; p: Vec2[] }>()
  predicted.forEach((p, i) => {
    const k = key(targets[i])
    if (!groups.has(k)) groups.set(k, { t: targets[i], p: [] })
    groups.get(k)!.p.push(p)
  })
  if (groups.size < MIN_STRETCH_DOTS) return [0, 1, 0, 1]
  const dots = [...groups.values()]
  const out: number[] = []
  for (const axis of [0, 1] as const) {
    const m = dots.map((d) => median(d.p.map((p) => p[axis])))
    const t = dots.map((d) => d.t[axis])
    if (Math.max(...m) - Math.min(...m) < 1e-6) {
      out.push(0, 1)
      continue
    }
    const gain = Math.min(Math.max(linearSlope(m, t), 1), MAX_EDGE_STRETCH)
    const mean = (v: number[]) => v.reduce((s, x) => s + x, 0) / v.length
    out.push(mean(t) - gain * mean(m), gain)
  }
  return out as GazeModel['stretch']
}

/** Screen fraction (x, y) for one feature pair. */
export function predict(model: GazeModel, f: Vec2): Vec2 {
  const [x, y] = predictRaw(model, expand(f))
  const [ox, gx, oy, gy] = model.stretch
  return [ox + gx * x, oy + gy * y]
}

/** Fits the model; throws when there are too few or invalid samples. */
export function fitModel(samples: Sample[]): GazeModel {
  if (samples.length < MIN_SAMPLES) throw new Error('Not enough calibration samples to fit a model.')
  const raw = samples.map((s) => expand(s.f))
  const targets = samples.map((s) => s.t)
  if (!raw.flat().every(Number.isFinite) || !targets.flat().every(Number.isFinite)) {
    throw new Error('Calibration data contains invalid values.')
  }
  // Every dot has the same total influence even if it got fewer frames.
  const keys = targets.map(key)
  const counts = new Map<string, number>()
  keys.forEach((k) => counts.set(k, (counts.get(k) ?? 0) + 1))
  const weights = keys.map((k) => 1 / counts.get(k)!)

  let fit = fitRows(raw, targets, weights)
  // One robust refit drops frames captured mid-saccade, per dot.
  const residual = raw.map((r, i) => {
    const p = predictRaw(fit, r)
    return Math.hypot(p[0] - targets[i][0], p[1] - targets[i][1])
  })
  const keep = raw.map(() => true)
  for (const k of counts.keys()) {
    const idx = keys.flatMap((kk, i) => (kk === k ? [i] : []))
    if (idx.length < MIN_GROUP_INLIERS + 2) continue
    const values = idx.map((i) => residual[i])
    const med = median(values)
    const mad = median(values.map((v) => Math.abs(v - med)))
    const cutoff = Math.max(OUTLIER_NORMALIZED_FLOOR, med + OUTLIER_MAD_MULTIPLIER * 1.4826 * mad)
    const inliers = idx.filter((i) => residual[i] <= cutoff)
    if (inliers.length >= MIN_GROUP_INLIERS) idx.forEach((i) => (keep[i] = inliers.includes(i)))
  }
  const pick = <T,>(arr: T[]) => arr.filter((_, i) => keep[i])
  fit = fitRows(pick(raw), pick(targets), pick(weights))
  const stretch = edgeStretch(pick(raw).map((r) => predictRaw(fit, r)), pick(targets))
  return { source: MODEL_SOURCE, version: MODEL_VERSION, ...fit, stretch }
}

/** RMS error of each dot's median prediction, as a screen fraction (PC fixation_error). */
export function fixationError(model: GazeModel, samples: Sample[]): number {
  const groups = new Map<string, { t: Vec2; p: Vec2[] }>()
  for (const s of samples) {
    const k = key(s.t)
    if (!groups.has(k)) groups.set(k, { t: s.t, p: [] })
    groups.get(k)!.p.push(predict(model, s.f))
  }
  const squared = [...groups.values()].map(({ t, p }) =>
    (median(p.map((v) => v[0])) - t[0]) ** 2 + (median(p.map((v) => v[1])) - t[1]) ** 2)
  return Math.sqrt(squared.reduce((s, v) => s + v, 0) / squared.length)
}

/** Accuracy percentage as the PC reports it: round((1 - error) * 100, 2), within 0-100. */
export const accuracyPercent = (error: number) =>
  Math.round(Math.min(Math.max((1 - error) * 100, 0), 100) * 100) / 100

/** A saved model is usable only if every number is present and finite. */
export function isGazeModel(value: unknown): value is GazeModel {
  const m = value as GazeModel
  const numbers = (a: unknown, n: number) =>
    Array.isArray(a) && a.length === n && a.every((v) => typeof v === 'number' && Number.isFinite(v))
  return !!m && m.source === MODEL_SOURCE && numbers(m.mean, 5) && numbers(m.scale, 5) &&
    numbers(m.coefX, 6) && numbers(m.coefY, 6) && numbers(m.stretch, 4)
}
