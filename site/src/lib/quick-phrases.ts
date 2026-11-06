import type { SpeechLang } from '@/lib/voices'

/** Quick Phrases on the Voice Communication keyboard tab, in each language. */
export const QUICK_PHRASES: Record<SpeechLang, string[]> = {
  en: ['I need help', 'Yes', 'No', 'Thank you', "I'm hungry", 'I need water', 'Please call my caregiver'],
  fil: [
    'Tulungan mo ako', 'Oo', 'Hindi', 'Salamat', 'Gutom na ako', 'Gusto ko ng tubig',
    'Pakitawag ang aking tagapag-alaga',
  ],
}
