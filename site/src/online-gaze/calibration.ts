/**
 * Online calibration rules, the PC's collector and processor
 * (server/app/core/calibration/collector.py, processor.py): 13 dots, frames
 * collected after the eyes settle on each dot, per-dot outlier removal, then
 * one fit judged by each dot's median error.
 */

import { median, fitModel, fixationError, MAX_FIT_ERROR_FRACTION, MAX_LOW_ACCURACY_FRACTION,
  type GazeModel, type Sample, type Vec2 } from './regression.ts'

const EDGE = 0.04
export const CALIBRATION_POINTS: Vec2[] = [
  [0.5, 0.5],
  [0.5, EDGE], [1 - EDGE, 0.5], [0.5, 1 - EDGE], [EDGE, 0.5],
  [EDGE, EDGE], [1 - EDGE, EDGE], [1 - EDGE, 1 - EDGE], [EDGE, 1 - EDGE],
  [0.29, 0.29], [0.71, 0.29],
  [0.71, 0.71], [0.29, 0.71],
]

/** Time for the eyes to land on a new dot before frames count. */
export const SETTLE_MS = 700
export const COLLECT_MS = 950
export const MAX_COLLECT_MS = 2600
export const MIN_SAMPLES_PER_POINT = 15
export const MAX_POINT_RETRIES = 2

const OUTLIER_MAD_MULTIPLIER = 3
const MIN_SAMPLES_TO_FILTER = 6
const FEATURE_MAD_FLOORS = [0.004, 0.004]

/** Which frames of one dot to keep: drops blinks, glances away and bad reads. */
export function outlierMask(rows: Vec2[]): boolean[] {
  if (rows.length < MIN_SAMPLES_TO_FILTER) return rows.map(() => true)
  const med = [0, 1].map((a) => median(rows.map((r) => r[a])))
  const mad = [0, 1].map((a) => Math.max(median(rows.map((r) => Math.abs(r[a] - med[a]))), FEATURE_MAD_FLOORS[a]))
  const keep = rows.map((r) => [0, 1].every((a) => Math.abs(r[a] - med[a]) / mad[a] <= OUTLIER_MAD_MULTIPLIER))
  return keep.some(Boolean) ? keep : rows.map(() => true)
}

export const cleaned = (rows: Vec2[]) => {
  const keep = outlierMask(rows)
  return rows.filter((_, i) => keep[i])
}

/** Whether collection at a dot can stop (enough clean frames, or out of time). */
export function dotFinished(rows: Vec2[], elapsedMs: number): boolean {
  if (elapsedMs >= MAX_COLLECT_MS) return true
  return elapsedMs >= COLLECT_MS && cleaned(rows).length >= MIN_SAMPLES_PER_POINT
}

export const dotHasEnough = (rows: Vec2[]) => cleaned(rows).length >= MIN_SAMPLES_PER_POINT

export type CalibrationOutcome =
  | { ok: true; model: GazeModel; error: number; lowAccuracy: boolean; sampleCount: number }
  | { ok: false; reason: 'fit_failed' | 'not_accurate_enough'; error: number | null; sampleCount: number }

/** Fits the dots' clean frames and applies the PC's acceptance limits. */
export function finishCalibration(dots: { target: Vec2; rows: Vec2[] }[]): CalibrationOutcome {
  const samples: Sample[] = dots.flatMap((d) => cleaned(d.rows).map((f) => ({ f, t: d.target })))
  let model: GazeModel
  try {
    model = fitModel(samples)
  } catch {
    return { ok: false, reason: 'fit_failed', error: null, sampleCount: samples.length }
  }
  const error = fixationError(model, samples)
  if (!Number.isFinite(error) || error > MAX_LOW_ACCURACY_FRACTION) {
    return { ok: false, reason: 'not_accurate_enough', error: Number.isFinite(error) ? error : null,
      sampleCount: samples.length }
  }
  return { ok: true, model, error, lowAccuracy: error > MAX_FIT_ERROR_FRACTION, sampleCount: samples.length }
}
