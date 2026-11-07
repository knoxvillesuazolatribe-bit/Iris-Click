import { Hand } from 'lucide-react'
import type { Gesture } from '@/validators/home-validator'

/** "Basic Functions": only the gestures the tracking worker performs today. */
export function GestureGuide({ gestures }: { gestures: Gesture[] }) {
  return (
    <section aria-labelledby="gesture-guide" className="bg-card w-full rounded-2xl border-2 p-6">
      <h2 id="gesture-guide" className="mb-4 flex items-center gap-3 text-2xl font-bold">
        <Hand className="size-8" aria-hidden />
        Basic Functions
      </h2>
      <dl className="grid gap-x-8 gap-y-3 text-xl sm:grid-cols-[auto_1fr]">
        {gestures.map(({ gesture, action }) => (
          <div key={gesture} className="contents">
            <dt className="font-semibold">{gesture}</dt>
            <dd className="text-muted-foreground mb-2 sm:mb-0">{action}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
