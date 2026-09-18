import { LogIn, UserPlus, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { useAuthContext } from '../../hooks/AuthContext'
import { Button } from '../ui'

interface AuthModalProps {
  onClose: () => void
}

const PIN_LENGTH = 2

export function AuthModal({ onClose }: AuthModalProps) {
  const { login, register, error } = useAuthContext()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [pin, setPin] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const pinIsValid = pin.length === PIN_LENGTH && /^\d+$/.test(pin)
  const canSubmit = username.trim().length > 0 && pinIsValid && !isSubmitting

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setIsSubmitting(true)
    const succeeded = mode === 'login' ? await login(username.trim(), pin) : await register(username.trim(), pin)
    setIsSubmitting(false)
    if (succeeded) onClose()
  }

  // Rendered via a portal to document.body rather than in place: this
  // component is triggered from inside <Header>, and <Header> has
  // backdrop-blur (backdrop-filter), which makes it the CSS containing
  // block for any `position: fixed` descendant — trapping the overlay
  // inside the 64px-tall header instead of the full viewport (confirmed
  // via computed-style inspection: the overlay's height came out as
  // exactly the header's height, not 100vh). A portal renders outside
  // that ancestor entirely, so `fixed inset-0` behaves correctly
  // regardless of which component happens to trigger the modal.
  return createPortal(
    <>
      <button
        aria-label="Close"
        className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto px-4 py-8">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200/80 bg-white shadow-[var(--shadow-lg)]">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
            <div className="flex items-center gap-2.5 text-[15px] font-semibold text-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-50 text-accent-600">
                {mode === 'login' ? <LogIn size={16} /> : <UserPlus size={16} />}
              </span>
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </div>
            <button
              aria-label="Close"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
            <p className="text-[12.5px] leading-relaxed text-slate-500">
              Signing in saves your conversation history to your own account. This is a lightweight demo login (a
              2-digit PIN), not intended to protect sensitive data.
            </p>

            <div>
              <label htmlFor="auth-username" className="mb-1.5 block text-[12.5px] font-medium text-slate-700">
                Username
              </label>
              <input
                id="auth-username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 outline-none focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20"
                placeholder="e.g. ojas"
              />
            </div>

            <div>
              <label htmlFor="auth-pin" className="mb-1.5 block text-[12.5px] font-medium text-slate-700">
                2-digit PIN
              </label>
              <input
                id="auth-pin"
                type="password"
                inputMode="numeric"
                autoComplete="current-password"
                maxLength={PIN_LENGTH}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, PIN_LENGTH))}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm tracking-[0.3em] text-slate-900 outline-none focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20"
                placeholder="00"
              />
            </div>

            {error && <p className="text-[12.5px] text-red-600">{error}</p>}

            <Button type="submit" className="w-full" isLoading={isSubmitting} disabled={!canSubmit}>
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>

            <button
              type="button"
              onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
              className="w-full text-center text-[12.5px] font-medium text-accent-600 hover:text-accent-700"
            >
              {mode === 'login' ? "Don't have an account? Create one" : 'Already have an account? Sign in'}
            </button>
          </form>
        </div>
      </div>
    </>,
    document.body,
  )
}
