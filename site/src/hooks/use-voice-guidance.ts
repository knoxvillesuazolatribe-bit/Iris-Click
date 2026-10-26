import { useEffect, useRef } from 'react'
import { useCalibrationStore } from '@/store/calibration-store'

const PROMPTS = {
  intro: 'Look at the centre of the screen. Calibration starts when both eyes are registered.',
  dots: 'Now follow each dot with your eyes only. Blink normally. Press Space for a rest.',
  paused: 'Paused. Take your time. Choose Resume when you are ready.',
  success: 'Calibration is complete. Eye tracking is starting. You can close this page.',
}
// Matches the desktop app: spoken guidance at or below about 150 words a minute.
const SPEECH_RATE = 0.9

function speak(text: string) {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = SPEECH_RATE
  window.speechSynthesis.speak(utterance)
}

/** Speaks short instructions on calibration milestones; the same text is always on screen. */
export function useVoiceGuidance() {
  const phase = useCalibrationStore((s) => s.phase)
  const paused = useCalibrationStore((s) => s.paused)
  const restMessage = useCalibrationStore((s) => s.restMessage)
  const advice = useCalibrationStore((s) => s.frame?.guidance ?? null)
  const error = useCalibrationStore((s) => s.error)
  const spokenAdvice = useRef(new Set<string>())

  useEffect(() => {
    if (phase === 'registering') speak(PROMPTS.intro)
    else if (phase === 'dots') speak(PROMPTS.dots)
    else if (phase === 'success') speak(PROMPTS.success)
    else if (phase === 'idle') spokenAdvice.current.clear()
  }, [phase])

  useEffect(() => {
    if (phase === 'failed' && error) speak(error)
  }, [phase, error])

  useEffect(() => {
    if (paused) speak(PROMPTS.paused)
  }, [paused])

  useEffect(() => {
    if (restMessage) speak(restMessage)
  }, [restMessage])

  useEffect(() => {
    if (!advice || phase !== 'registering' || spokenAdvice.current.has(advice)) return
    spokenAdvice.current.add(advice)
    speak(advice)
  }, [advice, phase])

  useEffect(() => () => window.speechSynthesis?.cancel(), [])
}
