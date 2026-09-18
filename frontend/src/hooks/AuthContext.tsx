import { createContext, useContext, type ReactNode } from 'react'
import { useAuth } from './useAuth'

type AuthContextValue = ReturnType<typeof useAuth>

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * A single useAuth() instance shared app-wide via context — logging in
 * from one place (e.g. the header's account menu) must be immediately
 * visible everywhere else (e.g. HistoryPage), which a per-component
 * useAuth() call could not guarantee.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuth()
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}

export function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuthContext must be used within an AuthProvider')
  return context
}
