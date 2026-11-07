/**
 * Google MediaPipe Face Landmarker in the browser (approved: tasks-vision 1.1.1,
 * Apache-2.0). The library loads from jsDelivr at runtime, so the site's
 * package.json and lockfile are untouched; the face model is served by the
 * site (public/models, the same file the PC uses). Camera frames are processed
 * on this device only and never uploaded.
 */

import type { Landmark } from './features'

const VERSION = '1.1.1'
const CDN = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}`
const MODEL_URL = '/models/face_landmarker.task'

interface FaceLandmarkerResult {
  faceLandmarks: Landmark[][]
}

export interface FaceLandmarker {
  detectForVideo(video: HTMLVideoElement, timestampMs: number): FaceLandmarkerResult
  close(): void
}

interface VisionModule {
  FilesetResolver: { forVisionTasks(basePath: string): Promise<unknown> }
  FaceLandmarker: {
    createFromOptions(fileset: unknown, options: Record<string, unknown>): Promise<FaceLandmarker>
  }
}

let loading: Promise<FaceLandmarker> | null = null

async function create(delegate: 'GPU' | 'CPU'): Promise<FaceLandmarker> {
  const vision = (await import(/* @vite-ignore */ `${CDN}/vision_bundle.mjs`)) as VisionModule
  const fileset = await vision.FilesetResolver.forVisionTasks(`${CDN}/wasm`)
  return vision.FaceLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate },
    runningMode: 'VIDEO',
    numFaces: 1,
    minFaceDetectionConfidence: 0.5,
    minFacePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  })
}

/** Loads the face tracker once (GPU, falling back to CPU). */
export function loadFaceLandmarker(): Promise<FaceLandmarker> {
  loading ??= create('GPU').catch(() => create('CPU')).catch((error: unknown) => {
    loading = null
    throw error
  })
  return loading
}
