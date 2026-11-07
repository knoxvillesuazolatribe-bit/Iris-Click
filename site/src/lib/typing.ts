export type KeyName = string

/** Applies one on-page key to the message; new sentences start with a capital letter. */
export function typeKey(text: string, key: KeyName, maxChars: number): string {
  if (key === 'BACKSPACE') return text.slice(0, -1)
  if (text.length >= maxChars) return text
  if (key === 'SPACE') return `${text} `
  if (key === 'ENTER') return `${text}\n`
  if (!/^[A-Z]$/.test(key)) return text + key
  const newSentence = text.trim() === '' || /[.?!]\s+$/.test(text) || /\n$/.test(text)
  return text + (newSentence ? key : key.toLowerCase())
}
