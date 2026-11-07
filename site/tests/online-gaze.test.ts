// Online eye tracking math (site/src/online-gaze). Run: node --test tests/
import assert from 'node:assert/strict'
import test from 'node:test'

import { DwellClicker, EdgeScroller } from '../src/online-gaze/actions.ts'
import { CALIBRATION_POINTS, finishCalibration, outlierMask } from '../src/online-gaze/calibration.ts'
import { distanceAdvice, readEyes, type Landmark, LEFT_EYE_CORNERS, LEFT_EYE_LIDS, LEFT_IRIS,
  RIGHT_EYE_CORNERS, RIGHT_EYE_LIDS, RIGHT_IRIS } from '../src/online-gaze/features.ts'
import { OneEuroFilter } from '../src/online-gaze/filters.ts'
import { accuracyPercent, fitModel, fixationError, isGazeModel, predict, type Sample,
  type Vec2 } from '../src/online-gaze/regression.ts'
import { chooseTarget, TargetLock, type Target } from '../src/online-gaze/targets.ts'
import { WinkDetector } from '../src/online-gaze/winks.ts'

// Deterministic pseudo-random numbers so failures repeat.
function random(seed = 7) {
  let s = seed
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648
    return s / 2147483648
  }
}

/** A face: eyes 0.14 of the frame apart, irises shifted by (ix, iy) eye-thirds, lids open by `open`. */
function face({ ix = 0, iy = 0, leftOpen = 0.3, rightOpen = 0.3 } = {}): Landmark[] {
  const lm: Landmark[] = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }))
  const eye = (cx: number, inner: number, outer: number, lids: readonly [number, number], iris: number[],
    open: number) => {
    const half = 0.025
    lm[inner] = { x: cx - half, y: 0.5 }
    lm[outer] = { x: cx + half, y: 0.5 }
    lm[lids[0]] = { x: cx, y: 0.5 - open * half }
    lm[lids[1]] = { x: cx, y: 0.5 + open * half }
    const unit = 0.14 / 3
    for (const i of iris) lm[i] = { x: cx + ix * unit, y: 0.5 + iy * unit }
  }
  eye(0.57, LEFT_EYE_CORNERS[0], LEFT_EYE_CORNERS[1], LEFT_EYE_LIDS, LEFT_IRIS, leftOpen)
  eye(0.43, RIGHT_EYE_CORNERS[0], RIGHT_EYE_CORNERS[1], RIGHT_EYE_LIDS, RIGHT_IRIS, rightOpen)
  return lm
}

test('eye reading: centred irises give zero, moved irises move it, eye spacing measured', () => {
  const still = readEyes(face(), 640, 480)!
  assert.ok(Math.abs(still.ex) < 1e-9 && Math.abs(still.ey) < 1e-9)
  assert.ok(Math.abs(still.eyeDistance - 0.14) < 1e-9)
  const moved = readEyes(face({ ix: 0.2, iy: -0.1 }), 640, 480)!
  assert.ok(Math.abs(moved.ex - 0.2) < 1e-6 && Math.abs(moved.ey - -0.1 * (480 / 640)) < 1e-6)
  // lid gap 2 x 0.3 x 0.025 of 480 px over a corner span of 0.05 of 640 px
  const ear = (2 * 0.3 * 0.025 * 480) / (0.05 * 640)
  assert.ok(Math.abs(still.leftEar - ear) < 1e-9 && Math.abs(still.rightEar - ear) < 1e-9)
  const winking = readEyes(face({ leftOpen: 0.05 }), 640, 480)!
  assert.ok(winking.leftEar < winking.rightEar * 0.6)
  assert.equal(readEyes(face().slice(0, 400), 640, 480), null)
  assert.equal(distanceAdvice(still), null)
})

/** Samples from a known smooth mapping, with noise, 25 frames per dot. */
function samplesFor(noise: number, seed = 3, perDot = 25): Sample[] {
  const r = random(seed)
  return CALIBRATION_POINTS.flatMap((t) => Array.from({ length: perDot }, () => {
    const ex = (t[0] - 0.5) * 0.5 + 0.05 * (t[0] - 0.5) ** 2 + (r() - 0.5) * noise
    const ey = (t[1] - 0.5) * 0.3 + (r() - 0.5) * noise
    return { f: [ex, ey] as Vec2, t }
  }))
}

test('the fit recovers a smooth mapping and reports a small per-dot error', () => {
  const samples = samplesFor(0.01)
  const model = fitModel(samples)
  assert.ok(isGazeModel(model))
  const error = fixationError(model, samples)
  assert.ok(error < 0.02, `error ${error}`)
  const [x, y] = predict(model, [0, 0])
  assert.ok(Math.abs(x - 0.5) < 0.03 && Math.abs(y - 0.5) < 0.03, `${x},${y}`)
  assert.equal(accuracyPercent(error), Math.round((1 - error) * 10000) / 100)
})

test('glances away at one dot are dropped by the robust refit', () => {
  const samples = samplesFor(0.005)
  const corner = samples.filter((s) => s.t[0] === 0.04 && s.t[1] === 0.04)
  corner.slice(0, 5).forEach((s) => (s.f = [0.3, 0.2])) // 5 of 25 frames looking elsewhere
  assert.ok(fixationError(fitModel(samples), samples) < 0.03)
})

test('calibration passes on clean eyes and fails on eyes that do not follow the dots', () => {
  const dots = CALIBRATION_POINTS.map((target) => ({
    target, rows: samplesFor(0.01).filter((s) => s.t === target).map((s) => s.f) }))
  const good = finishCalibration(dots)
  assert.ok(good.ok && !good.lowAccuracy)
  const r = random(11)
  const noisy = CALIBRATION_POINTS.map((target) => ({
    target, rows: Array.from({ length: 20 }, () => [(r() - 0.5) * 0.4, (r() - 0.5) * 0.4] as Vec2) }))
  const bad = finishCalibration(noisy)
  assert.ok(!bad.ok && bad.reason === 'not_accurate_enough')
  assert.deepEqual(finishCalibration([]), { ok: false, reason: 'fit_failed', error: null, sampleCount: 0 })
})

test('outlier mask drops a blink frame among steady frames', () => {
  const rows: Vec2[] = Array.from({ length: 12 }, (_, i) => [0.1 + (i % 3) * 0.001, -0.05])
  rows.push([0.4, 0.3])
  const keep = outlierMask(rows)
  assert.equal(keep.filter(Boolean).length, 12)
  assert.equal(keep[12], false)
})

test('a saved model with a missing number is not used', () => {
  const model = fitModel(samplesFor(0.01))
  assert.ok(isGazeModel(JSON.parse(JSON.stringify(model))))
  assert.equal(isGazeModel({ ...model, coefX: model.coefX.slice(1) }), false)
  assert.equal(isGazeModel(null), false)
})

test('winks: ordinary blinks never click, a held left wink does once', () => {
  const w = new WinkDetector(0.18, 350, 700)
  // ordinary blink, both eyes, 120 ms
  w.update(0.05, 0.05, 0)
  assert.equal(w.update(0.3, 0.3, 120), null)
  // uneven ordinary blink: left 0.15 is not below 0.6 x right 0.2
  w.update(0.15, 0.2, 1000)
  assert.equal(w.update(0.3, 0.3, 1500), null)
  // left wink held 400 ms
  assert.equal(w.update(0.08, 0.3, 3000), null)
  assert.ok(w.closing)
  assert.equal(w.update(0.3, 0.3, 3400), 'left')
  // a second wink inside the cool-down is ignored
  w.update(0.08, 0.3, 3500)
  assert.equal(w.update(0.3, 0.3, 3900), null)
  // right wink after the cool-down
  w.update(0.3, 0.08, 5000)
  assert.equal(w.update(0.3, 0.3, 5400), 'right')
  // a wink that turns into a full blink is a blink
  w.update(0.08, 0.3, 7000)
  w.update(0.05, 0.05, 7100)
  assert.equal(w.update(0.3, 0.3, 7500), 'both')
})

const box = (id: string, left: number, top: number, w = 200, h = 80): Target =>
  ({ id, left, top, right: left + w, bottom: top + h })

test('snapping picks the nearest button and switches only on clear intent', () => {
  const a = box('a', 100, 100)
  const b = box('b', 400, 100)
  assert.equal(chooseTarget(320, 140, [a, b], 140)?.id, 'a')
  assert.equal(chooseTarget(900, 900, [a, b], 140), null)

  const lock = new TargetLock(140)
  assert.equal(lock.snap(150, 120, [a, b], 0).target?.id, 'a')
  // b is nearer but only briefly: stays on a
  assert.equal(lock.snap(390, 120, [a, b], 0.05).target?.id, 'a')
  // still on b after the switch time: moves to b
  assert.equal(lock.snap(420, 120, [a, b], 0.25).target?.id, 'b')
  // far from everything long enough: released
  lock.snap(1200, 900, [a, b], 1)
  assert.equal(lock.snap(1200, 900, [a, b], 1.5).target, null)
})

test('dwell clicks once after resting, edge scroll repeats while looking at the edge', () => {
  const d = new DwellClicker(700, 45, 500)
  assert.equal(d.update(100, 100, 0), false)
  assert.equal(d.update(110, 100, 600), false)
  assert.equal(d.update(105, 102, 750), true)
  assert.equal(d.update(105, 102, 2000), false) // fires once per rest
  // frames every 30 ms: look at the top band for 1 s, the middle, then the bottom band
  const s = new EdgeScroller(700)
  const scrolls: [number, string][] = []
  for (let t = 0; t <= 3000; t += 30) {
    const y = t <= 1000 ? 10 : t <= 1500 ? 500 : 995
    const dir = s.update(y, 1000, t)
    if (dir) scrolls.push([t, dir])
  }
  // up at ~720 and ~930 ms; down from ~2250 ms, then every ~210 ms until 3000 ms
  assert.deepEqual(scrolls.map(([, d]) => d), ['up', 'up', 'down', 'down', 'down', 'down'])
  assert.ok(scrolls[0][0] >= 700) // only after resting on the edge for the dwell time
  assert.ok(scrolls[2][0] >= 1530 + 700)
})

test('smoothing steadies jitter but follows a real move', () => {
  const f = new OneEuroFilter(30, 0.8, 0.01)
  const r = random(5)
  let last = 0
  for (let i = 0; i < 60; i++) last = f.filter(500 + (r() - 0.5) * 40, i / 30)
  assert.ok(Math.abs(last - 500) < 10)
  for (let i = 60; i < 120; i++) last = f.filter(900, i / 30)
  assert.ok(Math.abs(last - 900) < 20)
})
