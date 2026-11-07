/**
 * Online eye tracking engine: camera → face landmarks → eye features → gaze
 * point → smoothing → snap to the nearest button → wink / dwell click and
 * edge scroll. It controls this website only (browsers cannot move the
 * computer's real mouse). Camera frames never leave the device.
 */

import { useSyncExternalStore } from 'react'
import { player } from '@/lib/natural-voice'
import { speak } from '@/lib/speech'
import type { AccessibilitySettings } from '@/validators/settings-validator'
import { DwellClicker, EdgeScroller } from './actions'
import { loadFaceLandmarker, type FaceLandmarker } from './face-tracker'
import { distanceAdvice, readEyes, type EyeReading, type Landmark } from './features'
import { OneEuroFilter2D, SMOOTHING_CUTOFF } from './filters'
import { predict, type GazeModel } from './regression'
import { TargetLock, type Target } from './targets'
import { BLINK_LEVELS, WinkDetector } from './winks'

export type GazeStatus = 'off' | 'starting' | 'camera' | 'tracking' | 'paused' | 'error'
export type Guidance = 'no_face' | 'closer' | 'back' | 'too_dark' | 'overexposed'

// The PC worker's spoken lines (tracking_worker.SPEECH, lighting.LIGHTING_GUIDANCE).
export const GUIDANCE_TEXT: Record<Guidance, string> = {
  no_face: 'I cannot see your face. Please face the camera.',
  closer: 'Please move forward a little. Your eyes are too small for the camera.',
  back: 'Please move back a little. You are too close to the camera.',
  too_dark: 'Your face is too dark. Add soft light in front of you.',
  overexposed: 'Your face is washed out. Move bright light away from the camera.',
}

// A problem is shown/spoken only once it lasts PERSIST_MS; the same line waits
// REPEAT_MS, any two lines GAP_MS (the PC's VoiceGuide pacing).
const PERSIST_MS = 1500
const REPEAT_MS = 25000
const GAP_MS = 6000
const TARGETS_EVERY_MS = 300
const LIGHTING_EVERY_MS = 1000
const SCROLL_STEP_FRACTION = 0.25

/** Elements the pointer can snap to and click. */
const TARGET_SELECTOR = [
  'button', 'a[href]', 'input:not([type="hidden"])', 'textarea', 'select', 'summary',
  '[role="button"]', '[role="link"]', '[role="tab"]', '[role="radio"]', '[role="checkbox"]',
  '[role="switch"]', '[role="option"]', '[role="menuitem"]', '[data-gaze-target]',
].join(',')

export interface TrackerSettings {
  dwellEnabled: boolean
  dwellMs: number
  smoothing: 'low' | 'medium' | 'high'
  blinkToClick: boolean
  blinkSensitivity: number
  edgeScroll: boolean
  voiceVolume: number
}

export const DEFAULT_SETTINGS: TrackerSettings = {
  dwellEnabled: false, dwellMs: 700, smoothing: 'medium', blinkToClick: true,
  blinkSensitivity: 3, edgeScroll: true, voiceVolume: 100,
}

export const toTrackerSettings = (s: AccessibilitySettings): TrackerSettings => ({
  dwellEnabled: s.dwell_enabled, dwellMs: s.dwell_ms, smoothing: s.smoothing,
  blinkToClick: s.blink_to_click, blinkSensitivity: s.blink_sensitivity,
  edgeScroll: s.edge_scroll_enabled, voiceVolume: s.voice_volume,
})

export interface GazeSnapshot {
  status: GazeStatus
  error: string | null
  /** A problem that has lasted long enough to show. */
  guidance: Guidance | null
  faceVisible: boolean
  pointer: { x: number; y: number } | null
  target: { left: number; top: number; width: number; height: number } | null
  /** Dwell progress 0..1. */
  dwell: number
  /** An eye is closing: the pointer holds still. */
  closing: boolean
  /** performance.now() of the last click. */
  clickedAt: number
  /** True just after a click, for the pointer's click flash. */
  flash: boolean
}

const CLICK_FLASH_MS = 250

type ReadingListener = (reading: EyeReading | null, now: number) => void

const INITIAL: GazeSnapshot = {
  status: 'off', error: null, guidance: null, faceVisible: false, pointer: null, target: null,
  dwell: 0, closing: false, clickedAt: 0, flash: false,
}

function cameraError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'The camera is blocked. Allow the camera for this site (the camera icon in the address bar), then try again.'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No camera was found. Connect a webcam and try again.'
  if (name === 'NotReadableError') return 'The camera is busy in another app. Close that app and try again.'
  return 'The eye-tracking engine could not load. Check the internet connection and try again.'
}

class GazeEngine {
  private snapshot: GazeSnapshot = INITIAL
  private listeners = new Set<() => void>()
  private readingListeners = new Set<ReadingListener>()

  stream: MediaStream | null = null
  private video: HTMLVideoElement | null = null
  private landmarker: FaceLandmarker | null = null
  private raf = 0
  private lastVideoTime = -1
  private starting: Promise<void> | null = null

  private model: GazeModel | null = null
  private settings: TrackerSettings = DEFAULT_SETTINGS
  private filter = new OneEuroFilter2D(SMOOTHING_CUTOFF.medium)
  private wink = new WinkDetector()
  private lock = new TargetLock()
  private dweller = new DwellClicker()
  private scroller = new EdgeScroller()
  private targets: Target[] = []
  private targetsAt = -Infinity

  private problem: Guidance | null = null
  private problemSince = 0
  private spokenAt = new Map<Guidance, number>()
  private lastSpoken = -Infinity
  private lighting: Guidance | null = null
  private lightingAt = -Infinity
  private canvas: HTMLCanvasElement | null = null

  // --- store ---------------------------------------------------------------------------------
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  getSnapshot = () => this.snapshot

  private set(change: Partial<GazeSnapshot>) {
    this.snapshot = { ...this.snapshot, ...change }
    this.listeners.forEach((l) => l())
  }

  /** Raw eye readings, for the calibration page. */
  onReading(listener: ReadingListener) {
    this.readingListeners.add(listener)
    return () => this.readingListeners.delete(listener)
  }

  // --- camera --------------------------------------------------------------------------------
  /** Opens the camera and loads the face tracker (once). */
  startCamera(): Promise<void> {
    if (this.stream && this.landmarker) return Promise.resolve()
    this.starting ??= this.open().finally(() => (this.starting = null))
    return this.starting
  }

  private async open() {
    this.set({ status: 'starting', error: null })
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
      })
      const video = document.createElement('video')
      video.muted = true
      video.playsInline = true
      video.srcObject = stream
      await video.play()
      this.stream = stream
      this.video = video
      this.landmarker = await loadFaceLandmarker()
      this.set({ status: this.model ? 'tracking' : 'camera' })
      cancelAnimationFrame(this.raf)
      this.raf = requestAnimationFrame(this.loop)
    } catch (error) {
      this.closeCamera()
      this.set({ status: 'error', error: cameraError(error) })
      throw error
    }
  }

  private closeCamera() {
    cancelAnimationFrame(this.raf)
    this.stream?.getTracks().forEach((t) => t.stop())
    this.stream = null
    if (this.video) this.video.srcObject = null
    this.video = null
    this.lastVideoTime = -1
  }

  // --- tracking ------------------------------------------------------------------------------
  async startTracking(model: GazeModel, settings: TrackerSettings) {
    this.model = model
    this.applySettings(settings)
    this.resetMotion()
    await this.startCamera()
    this.set({ status: 'tracking', error: null })
  }

  applySettings(settings: TrackerSettings) {
    this.settings = settings
    this.filter = new OneEuroFilter2D(SMOOTHING_CUTOFF[settings.smoothing])
    this.wink.threshold = BLINK_LEVELS[Math.min(Math.max(settings.blinkSensitivity, 1), 5) - 1]
    this.dweller.dwellMs = settings.dwellMs
    this.scroller.dwellMs = settings.dwellMs
  }

  pause() {
    if (this.snapshot.status !== 'tracking') return
    this.resetMotion()
    this.set({ status: 'paused', pointer: null, target: null, dwell: 0 })
  }

  resume() {
    if (this.snapshot.status === 'paused' && this.model) this.set({ status: 'tracking' })
  }

  /** Stops tracking and turns the camera off. */
  stop() {
    this.model = null
    this.closeCamera()
    this.resetMotion()
    this.set({ ...INITIAL })
  }

  /** Keeps the camera for calibration but stops moving the pointer. */
  stopTracking() {
    this.model = null
    this.resetMotion()
    this.set({ status: this.stream ? 'camera' : 'off', pointer: null, target: null, dwell: 0 })
  }

  private resetMotion() {
    this.filter.reset()
    this.wink.reset()
    this.lock.reset()
    this.dweller.reset()
    this.targetsAt = -Infinity
  }

  private loop = () => {
    this.raf = requestAnimationFrame(this.loop)
    const video = this.video
    if (!video || !this.landmarker || video.readyState < 2 || video.currentTime === this.lastVideoTime) return
    this.lastVideoTime = video.currentTime
    const now = performance.now()
    let landmarks: Landmark[] | undefined
    try {
      landmarks = this.landmarker.detectForVideo(video, now).faceLandmarks?.[0]
    } catch {
      return
    }
    const reading = landmarks ? readEyes(landmarks, video.videoWidth, video.videoHeight) : null
    this.readingListeners.forEach((l) => l(reading, now))
    this.updateGuidance(reading, landmarks, video, now)
    if (this.snapshot.status === 'tracking' && this.model) this.track(reading, now)
    else if (this.snapshot.faceVisible !== !!reading) this.set({ faceVisible: !!reading })
  }

  private track(reading: EyeReading | null, now: number) {
    if (!reading) {
      this.dweller.reset()
      this.set({ faceVisible: false, dwell: 0, closing: false })
      return
    }
    const s = this.settings
    if (s.blinkToClick) {
      const gesture = this.wink.update(reading.leftEar, reading.rightEar, now)
      if (gesture === 'left') this.clickTarget(now)
      else if (gesture === 'right') window.history.back()
      // The pointer holds still while an eye closes, so a wink clicks where you looked.
      if (this.wink.closing) {
        if (!this.snapshot.closing) this.set({ closing: true, faceVisible: true })
        return
      }
    }
    const w = window.innerWidth
    const h = window.innerHeight
    const [fx, fy] = predict(this.model!, [reading.ex, reading.ey])
    const gx = Math.min(Math.max(fx * w, 0), w - 1)
    const gy = Math.min(Math.max(fy * h, 0), h - 1)
    const [x, y] = this.filter.filter(gx, gy, now / 1000)

    if (now - this.targetsAt >= TARGETS_EVERY_MS) {
      this.targets = collectTargets()
      this.targetsAt = now
    }
    const snapped = this.lock.snap(x, y, this.targets, now / 1000)
    let dwell = 0
    if (s.dwellEnabled) {
      if (this.dweller.update(snapped.x, snapped.y, now) && snapped.target) this.clickTarget(now)
      dwell = snapped.target ? this.dweller.progress(now) : 0
    }
    if (s.edgeScroll && !overControlBar(x, y)) {
      const direction = this.scroller.update(y, h, now)
      if (direction) scrollAt(x, y, direction === 'up' ? -1 : 1)
    }
    const el = snapped.target?.id as HTMLElement | undefined
    const rect = el?.getBoundingClientRect()
    this.set({
      faceVisible: true, closing: false, dwell, flash: now - this.snapshot.clickedAt < CLICK_FLASH_MS,
      // Snapped: the pointer sits on the button's centre, as on the PC.
      pointer: { x: snapped.x, y: snapped.y },
      target: rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null,
    })
  }

  private clickTarget(now: number) {
    const el = this.lock.active?.id as HTMLElement | undefined
    if (!el || !el.isConnected || (el as HTMLButtonElement).disabled) return
    el.focus({ preventScroll: true })
    el.click()
    this.dweller.reset()
    this.targetsAt = -Infinity
    this.set({ clickedAt: now, flash: true })
  }

  // --- guidance ------------------------------------------------------------------------------
  private updateGuidance(reading: EyeReading | null, landmarks: Landmark[] | undefined,
    video: HTMLVideoElement, now: number) {
    if (now - this.lightingAt >= LIGHTING_EVERY_MS) {
      this.lightingAt = now
      this.lighting = landmarks ? this.lightingStatus(video, landmarks) : null
    }
    const problem: Guidance | null = !landmarks ? 'no_face' : !reading ? 'no_face'
      : distanceAdvice(reading) ?? this.lighting
    if (problem !== this.problem) {
      this.problem = problem
      this.problemSince = now
    }
    const shown = problem && now - this.problemSince >= PERSIST_MS ? problem : null
    if (shown !== this.snapshot.guidance) this.set({ guidance: shown })
    if (shown && this.snapshot.status === 'tracking') this.say(shown, now)
  }

  private say(problem: Guidance, now: number) {
    const volume = this.settings.voiceVolume
    if (volume <= 0 || now - (this.spokenAt.get(problem) ?? -Infinity) < REPEAT_MS || now - this.lastSpoken < GAP_MS) return
    // Never talk over the user's own message.
    if (player.snapshot().speaking || window.speechSynthesis?.speaking) return
    if (speak(GUIDANCE_TEXT[problem], volume)) {
      this.spokenAt.set(problem, now)
      this.lastSpoken = now
    }
  }

  /** "too_dark", "overexposed" or null, from the face area's brightness (PC rules). */
  private lightingStatus(video: HTMLVideoElement, landmarks: Landmark[]): Guidance | null {
    try {
      this.canvas ??= document.createElement('canvas')
      const cw = 96
      const ch = Math.max(1, Math.round((cw * video.videoHeight) / video.videoWidth))
      this.canvas.width = cw
      this.canvas.height = ch
      const ctx = this.canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) return null
      ctx.drawImage(video, 0, 0, cw, ch)
      const xs = landmarks.slice(0, 468).map((p) => p.x * cw)
      const ys = landmarks.slice(0, 468).map((p) => p.y * ch)
      const x0 = Math.max(0, Math.floor(Math.min(...xs)))
      const y0 = Math.max(0, Math.floor(Math.min(...ys)))
      const x1 = Math.min(cw, Math.ceil(Math.max(...xs)))
      const y1 = Math.min(ch, Math.ceil(Math.max(...ys)))
      if (x1 - x0 < 4 || y1 - y0 < 4) return null
      const data = ctx.getImageData(x0, y0, x1 - x0, y1 - y0).data
      const gray: number[] = []
      for (let i = 0; i < data.length; i += 4) gray.push(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2])
      gray.sort((a, b) => a - b)
      const median = gray[gray.length >> 1]
      const dark = gray.filter((v) => v <= 20).length / gray.length
      const bright = gray.filter((v) => v >= 245).length / gray.length
      if (median < 35 || dark > 0.6) return 'too_dark'
      if (median > 230 || bright > 0.6) return 'overexposed'
    } catch {
      return null
    }
    return null
  }
}

/** Visible, enabled, unobstructed controls in the viewport. */
function collectTargets(): Target[] {
  const w = window.innerWidth
  const h = window.innerHeight
  const out: Target[] = []
  for (const el of document.querySelectorAll<HTMLElement>(TARGET_SELECTOR)) {
    if ((el as HTMLButtonElement).disabled || el.closest('[data-gaze-ignore],[aria-hidden="true"],[inert]')) continue
    const r = el.getBoundingClientRect()
    if (r.width < 4 || r.height < 4 || r.right <= 0 || r.bottom <= 0 || r.left >= w || r.top >= h) continue
    // Skip controls covered by something else (an open dialog, for example).
    const cx = Math.min(Math.max((r.left + r.right) / 2, 0), w - 1)
    const cy = Math.min(Math.max((r.top + r.bottom) / 2, 0), h - 1)
    const top = document.elementFromPoint(cx, cy)
    if (top && top !== el && !el.contains(top) && !top.contains(el)) continue
    out.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom, id: el })
  }
  return out
}

function overControlBar(x: number, y: number): boolean {
  const bar = document.querySelector('[data-gaze-bar]')
  if (!bar) return false
  const r = bar.getBoundingClientRect()
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
}

/** Scrolls the scrollable area under the pointer (or the page). */
function scrollAt(x: number, y: number, direction: 1 | -1) {
  let el = document.elementFromPoint(x, y) as HTMLElement | null
  while (el && el !== document.body) {
    const style = getComputedStyle(el)
    if (/(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 1) {
      el.scrollBy({ top: direction * el.clientHeight * SCROLL_STEP_FRACTION, behavior: 'smooth' })
      return
    }
    el = el.parentElement
  }
  window.scrollBy({ top: direction * window.innerHeight * SCROLL_STEP_FRACTION, behavior: 'smooth' })
}

export const gaze = new GazeEngine()

export function useGaze(): GazeSnapshot {
  return useSyncExternalStore(gaze.subscribe, gaze.getSnapshot)
}

export function useGazeStatus(): GazeStatus {
  return useSyncExternalStore(gaze.subscribe, () => gaze.getSnapshot().status)
}
