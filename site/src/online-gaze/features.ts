/**
 * Eye features from MediaPipe face landmarks, the same as the PC's
 * eye_midpoint_v1 source (server/app/core/detection/iris_detector.py):
 * the midpoint between both irises measured along the line through the two
 * eye centres, in thirds of the eye spacing. Head translation, tilt and
 * camera distance cancel; only eye rotation moves it.
 */

export interface Landmark {
  x: number
  y: number
}

// MediaPipe Face Mesh indices (same as the PC).
export const LEFT_IRIS = [474, 475, 476, 477]
export const RIGHT_IRIS = [469, 470, 471, 472]
export const LEFT_EYE_CORNERS = [362, 263] as const // inner, outer
export const RIGHT_EYE_CORNERS = [33, 133] as const
export const LEFT_EYE_LIDS = [386, 374] as const // top, bottom
export const RIGHT_EYE_LIDS = [159, 145] as const

const EYE_LINE_UNIT_FRACTION = 1 / 3
// Comfortable eye-centre spacing as a fraction of the frame width (PC values).
export const EYE_DISTANCE_MIN = 0.105
export const EYE_DISTANCE_MAX = 0.19

export interface EyeReading {
  /** Eye-midpoint offset (ex, ey) in eye-spacing thirds. */
  ex: number
  ey: number
  leftEar: number
  rightEar: number
  /** Eye-centre spacing as a fraction of the frame width. */
  eyeDistance: number
}

type Point = [number, number]

const pt = (lm: Landmark[], i: number, w: number, h: number): Point => [lm[i].x * w, lm[i].y * h]
const mid = (a: Point, b: Point): Point => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
const sub = (a: Point, b: Point): Point => [a[0] - b[0], a[1] - b[1]]
const dot = (a: Point, b: Point) => a[0] * b[0] + a[1] * b[1]
const norm = (a: Point) => Math.hypot(a[0], a[1])

function centre(lm: Landmark[], indices: number[], w: number, h: number): Point {
  let x = 0
  let y = 0
  for (const i of indices) {
    x += lm[i].x * w
    y += lm[i].y * h
  }
  return [x / indices.length, y / indices.length]
}

/** Eye aspect ratio: lid gap over corner span (lower = more closed). */
export function eyeAspectRatio(lm: Landmark[], lids: readonly [number, number],
  corners: readonly [number, number], w: number, h: number): number {
  const horizontal = norm(sub(pt(lm, corners[0], w, h), pt(lm, corners[1], w, h)))
  if (horizontal === 0) return 1
  return norm(sub(pt(lm, lids[0], w, h), pt(lm, lids[1], w, h))) / horizontal
}

/** One frame's eye reading, or null when the face is too small or missing points. */
export function readEyes(lm: Landmark[] | undefined, w: number, h: number): EyeReading | null {
  if (!lm || lm.length < 478 || w <= 0 || h <= 0) return null
  const leftIris = centre(lm, LEFT_IRIS, w, h)
  const rightIris = centre(lm, RIGHT_IRIS, w, h)
  const leftEye = mid(pt(lm, LEFT_EYE_CORNERS[0], w, h), pt(lm, LEFT_EYE_CORNERS[1], w, h))
  const rightEye = mid(pt(lm, RIGHT_EYE_CORNERS[0], w, h), pt(lm, RIGHT_EYE_CORNERS[1], w, h))

  const axis = sub(leftEye, rightEye)
  const distance = norm(axis)
  if (distance <= 1e-6) return null
  const along: Point = [axis[0] / distance, axis[1] / distance]
  const across: Point = [-along[1], along[0]]
  const unit = distance * EYE_LINE_UNIT_FRACTION
  const offset = sub(mid(leftIris, rightIris), mid(leftEye, rightEye))

  const reading: EyeReading = {
    ex: dot(offset, along) / unit,
    ey: dot(offset, across) / unit,
    leftEar: eyeAspectRatio(lm, LEFT_EYE_LIDS, LEFT_EYE_CORNERS, w, h),
    rightEar: eyeAspectRatio(lm, RIGHT_EYE_LIDS, RIGHT_EYE_CORNERS, w, h),
    eyeDistance: distance / w,
  }
  return Object.values(reading).every(Number.isFinite) ? reading : null
}

/** "closer", "back" or null, from the eye spacing (PC distance_advice). */
export function distanceAdvice(reading: EyeReading): 'closer' | 'back' | null {
  if (reading.eyeDistance < EYE_DISTANCE_MIN) return 'closer'
  if (reading.eyeDistance > EYE_DISTANCE_MAX) return 'back'
  return null
}
