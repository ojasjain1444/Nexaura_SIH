import { LogOut, User } from 'lucide-react'
import { useState } from 'react'
import { AuthModal } from '../components/auth/AuthModal'
import { useAuthContext } from '../hooks/AuthContext'

export function AccountMenu() {
  const { user, isLoading, logout } = useAuthContext()
  const [accountOpen, setAccountOpen] = useState(false)
  const [authModalOpen, setAuthModalOpen] = useState(false)

  // Avoids a "Sign in" flash for an already-logged-in user on every page
  // load: a stored token is re-validated against the backend on mount
  // (see useAuth.ts), which takes a moment — showing neither state until
  // that resolves is less jarring than briefly showing the wrong one.
  if (isLoading) {
    return <div className="h-8 w-20 animate-pulse rounded-full bg-slate-100" aria-hidden="true" />
  }

  if (!user) {
    return (
      <>
        <button
          onClick={() => setAuthModalOpen(true)}
          className="flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1.5 text-[13px] font-medium text-slate-600 hover:bg-slate-50"
        >
          <User size={14.5} />
          <span className="hidden sm:inline">Sign in</span>
        </button>
        {authModalOpen && <AuthModal onClose={() => setAuthModalOpen(false)} />}
      </>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => setAccountOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={accountOpen}
        className="flex items-center gap-2 rounded-full border border-slate-200 py-1 pl-1 pr-3 text-[13px] font-medium text-slate-700 hover:bg-slate-50"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-accent-400 to-accent-600 text-[11px] font-bold text-white">
          {user.username.charAt(0).toUpperCase()}
        </span>
        <span className="hidden sm:inline">{user.username}</span>
      </button>
      {accountOpen && (
        <>
          <button
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setAccountOpen(false)}
          />
          <ul
            role="menu"
            className="absolute right-0 z-20 mt-2 w-44 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-[var(--shadow-lg)]"
          >
            <li>
              <button
                role="menuitem"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
                onClick={() => {
                  logout()
                  setAccountOpen(false)
                }}
              >
                <LogOut size={14} /> Sign out
              </button>
            </li>
          </ul>
        </>
      )}
    </div>
  )
}
