import { useCallback, useEffect, useState } from 'react'
import {
  type AuthUser,
  getCurrentUser,
  getStoredAuthToken,
  loginUser,
  logoutUser,
  registerUser,
  setStoredAuthToken,
} from '../services/api'

/**
 * Auth is entirely optional — the app fully works signed out (see
 * backend app/api/deps.py's get_optional_current_user). Logging in only
 * adds a personal, saved conversation history; it is never required to
 * chat. A stored token is validated once on mount (GET /api/auth/me) so
 * a stale/expired token clears itself instead of silently pretending the
 * user is still logged in.
 */
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!getStoredAuthToken()) {
      setIsLoading(false)
      return
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => {
        // Token is stale/expired/invalid — degrade to signed-out rather
        // than keep showing a user that the backend no longer recognizes.
        setStoredAuthToken(null)
      })
      .finally(() => setIsLoading(false))
  }, [])

  const register = useCallback(async (username: string, pin: string) => {
    setError(null)
    try {
      const result = await registerUser(username, pin)
      setStoredAuthToken(result.token)
      setUser(result.user)
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
      return false
    }
  }, [])

  const login = useCallback(async (username: string, pin: string) => {
    setError(null)
    try {
      const result = await loginUser(username, pin)
      setStoredAuthToken(result.token)
      setUser(result.user)
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
      return false
    }
  }, [])

  const logout = useCallback(() => {
    logoutUser().catch(() => {
      // Best-effort server-side session invalidation — the client-side
      // sign-out below happens regardless, matching how useLanguage
      // treats an unreachable backend as non-fatal.
    })
    setStoredAuthToken(null)
    setUser(null)
  }, [])

  return { user, isLoading, error, register, login, logout }
}
