import { useEffect, useRef } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import type { EyeLine } from '@/validators/calibration-validator'

interface GazePreviewProps {
  eyeLine: EyeLine | null
}

// Eye rotation moves the irises only a few pixels; magnify the pointer offset.
const POINTER_MAGNIFY = 8
const CANVAS_W = 480
const CANVAS_H = 300
// Eyes sit high so the nose apex of the "0 V 0" pyramid fits below them.
const EYE_LINE_Y = CANVAS_H * 0.3
const EYE_HALF_SPAN = CANVAS_W * 0.22

function themeColour(element: HTMLElement, token: string) {
  return getComputedStyle(element).getPropertyValue(token).trim() || 'currentColor'
}

/**
 * Custom (no shadcn equivalent): the "0 V 0" schematic — both irises, the V
 * down to the nose tip, and the pupil-midpoint pointer — drawn from landmarks
 * only. No camera image is shown.
 */
export function GazePreview({ eyeLine }: GazePreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H)
    if (!eyeLine) return

    const line = themeColour(canvas, '--muted-foreground')
    const iris = themeColour(canvas, '--foreground')
    const pointer = themeColour(canvas, '--primary')
    const cx = CANVAS_W / 2
    const cy = EYE_LINE_Y
    const [lx, ly] = eyeLine.left_eye
    const [rx, ry] = eyeLine.right_eye
    const [mx, my] = eyeLine.line_centre
    const span = Math.max(1e-6, Math.hypot(lx - rx, ly - ry))
    const toMap = ([px, py]: readonly [number, number]) =>
      [cx + ((px - mx) / span) * 2 * EYE_HALF_SPAN, cy + ((py - my) / span) * 2 * EYE_HALF_SPAN] as const

    const [ex, ey] = toMap(eyeLine.left_eye)
    const [fx, fy] = toMap(eyeLine.right_eye)
    ctx.lineWidth = 2
    ctx.strokeStyle = line
    ctx.beginPath()
    ctx.moveTo(ex, ey)
    ctx.lineTo(fx, fy)
    ctx.stroke()

    if (eyeLine.nose_tip) {
      const [tx, ty] = toMap(eyeLine.nose_tip)
      const [ax, ay] = toMap(eyeLine.left_iris)
      const [bx, by] = toMap(eyeLine.right_iris)
      ctx.beginPath()
      ctx.moveTo(ax, ay)
      ctx.lineTo(tx, ty)
      ctx.lineTo(bx, by)
      ctx.stroke()
      ctx.fillStyle = line
      ctx.beginPath()
      ctx.arc(tx, ty, 5, 0, Math.PI * 2)
      ctx.fill()
    }

    ctx.strokeStyle = iris
    for (const point of [eyeLine.left_iris, eyeLine.right_iris]) {
      const [ix, iy] = toMap(point)
      ctx.beginPath()
      ctx.arc(ix, iy, 16, 0, Math.PI * 2)
      ctx.stroke()
    }

    const [px, py] = toMap(eyeLine.pointer)
    ctx.strokeStyle = pointer
    ctx.fillStyle = pointer
    ctx.lineWidth = 4
    ctx.beginPath()
    ctx.arc(cx + (px - cx) * POINTER_MAGNIFY, cy + (py - cy) * POINTER_MAGNIFY, 18, 0, Math.PI * 2)
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(cx + (px - cx) * POINTER_MAGNIFY, cy + (py - cy) * POINTER_MAGNIFY, 3, 0, Math.PI * 2)
    ctx.fill()
  }, [eyeLine])

  return (
    <Card className="w-[min(90vw,520px)]">
      <CardContent className="relative flex items-center justify-center">
        <canvas
          ref={canvasRef}
          width={CANVAS_W}
          height={CANVAS_H}
          className="h-auto w-full"
          role="img"
          aria-label={eyeLine ? 'Both eyes found' : 'Looking for your eyes'}
        />
        {!eyeLine && (
          <p className="text-muted-foreground absolute text-lg">Looking for your eyes…</p>
        )}
      </CardContent>
    </Card>
  )
}
