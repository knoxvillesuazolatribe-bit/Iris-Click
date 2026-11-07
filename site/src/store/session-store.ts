import { create } from 'zustand'
import { errorMessage, errorStatus } from '@/api/app-client'
import { authService, assistiveService } from '@/services/auth-service'
import type { AdminLoginInput, SessionUser } from '@/validators/auth-validator'

export type SessionStatus = 'unknown' | 'loading' | 'signed-in' | 'signed-out' | 'offline'

interface SessionState {
  status: SessionStatus
  user: SessionUser | null
  /** Ask the server who is signed in on this browser. */
  load: () => Promise<void>
  /** Returns an error message to show, or null on success. */
  adminLogin: (input: AdminLoginInput) => Promise<string | null>
  selectUser: (userId: number) => Promise<string | null>
  logout: () => Promise<void>
}

export const useSessionStore = create<SessionState>((set, get) => ({
  status: 'unknown',
  user: null,

  load: async () => {
    if (get().status === 'loading') return
    set({ status: 'loading' })
    try {
      set({ status: 'signed-in', user: await authService.me() })
    } catch (error) {
      const code = errorStatus(error)
      set({ status: code === null || code >= 500 ? 'offline' : 'signed-out', user: null })
    }
  },

  adminLogin: async (input) => {
    try {
      set({ status: 'signed-in', user: await authService.adminLogin(input) })
      return null
    } catch (error) {
      return errorMessage(error, 'Sign-in failed. Please try again.')
    }
  },

  selectUser: async (userId) => {
    try {
      set({ status: 'signed-in', user: await assistiveService.select(userId) })
      return null
    } catch (error) {
      return errorMessage(error, 'Could not sign you in. Please try again.')
    }
  },

  logout: async () => {
    try {
      await authService.logout()
    } finally {
      // Signed out locally even if the server was unreachable.
      set({ status: 'signed-out', user: null })
    }
  },
}))
