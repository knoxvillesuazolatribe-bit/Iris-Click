import type { ComponentProps } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * Button sized for gaze + wink: at least 80 px tall, large text, and a thick
 * ring while the cursor rests on it so the user sees what a wink will press.
 */
export function GazeButton({ className, ...props }: ComponentProps<typeof Button>) {
  return (
    <Button
      size="lg"
      className={cn(
        'min-h-20 gap-3 rounded-xl px-8 text-xl font-semibold',
        "[&_svg:not([class*='size-'])]:size-7",
        'hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
        className,
      )}
      {...props}
    />
  )
}
