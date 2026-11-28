/**
 * Valid-data checks shown live on screen (panel revision). They mirror the server's rules
 * (user_apps_service.clean_url), which still decide: the page only explains early.
 */

export type Check = { valid: boolean; message: string; value?: string }

const UNSAFE = /["<>\\^`{|}]/

/** http/https only, a real domain ("youtube.com" becomes "https://youtube.com"), no spaces or hidden user name. */
export function checkWebsiteAddress(raw: string): Check {
  let url = raw.trim()
  if (!url) return { valid: false, message: 'Type the website address.' }
  if (/\s/.test(url)) return { valid: false, message: 'A website address cannot contain spaces.' }
  if (UNSAFE.test(url)) return { valid: false, message: 'That address has characters that are not allowed.' }
  if (!url.includes('://') && !url.split('/')[0].includes(':')) url = `https://${url}`
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return { valid: false, message: 'That is not a website address.' }
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname.includes('.')) {
    return { valid: false, message: 'Only http:// or https:// websites with a real domain, like https://www.facebook.com.' }
  }
  if (parsed.username || parsed.password) {
    return { valid: false, message: 'Type the address without a name or password in it.' }
  }
  return { valid: true, message: `Valid website address: ${url}`, value: url }
}
