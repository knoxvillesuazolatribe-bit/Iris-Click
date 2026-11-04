import axios, { isAxiosError } from 'axios'

/**
 * Client for the account pages (sign-in, home, admin). It calls /api on the
 * site's own origin; Vite proxies it to the server, so the httpOnly session
 * cookie is first-party and sent automatically.
 */
export const appClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

export const SERVER_DOWN_MESSAGE =
  'Cannot reach the IrisClick server. Make sure it is running, then try again.'

/** HTTP status of a failed request, or null when the server was not reached. */
export function errorStatus(error: unknown): number | null {
  if (!isAxiosError(error) || !error.response) return null
  // The dev proxy answers 502/504 when the server itself is down.
  if (error.response.status === 502 || error.response.status === 504) return null
  return error.response.status
}

/** The server's own message for a failed request, or a plain fallback. */
export function errorMessage(error: unknown, fallback = SERVER_DOWN_MESSAGE): string {
  if (errorStatus(error) === null) return SERVER_DOWN_MESSAGE
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
  return typeof detail === 'string' ? detail : fallback
}
