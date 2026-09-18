import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'inverse' | 'inverse-outline'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
  isLoading?: boolean
}

const variantClasses: Record<ButtonVariant, string> = {
  // The one accent color in the system, reserved for the primary action —
  // a real glow shadow on hover instead of just a darker fill, so the
  // "this is the button to press" signal reads as considered, not generic.
  primary:
    'bg-accent-500 text-white shadow-[var(--shadow-sm)] hover:bg-accent-600 hover:shadow-[var(--shadow-glow)] disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none',
  secondary: 'bg-white text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-50 hover:ring-slate-300 disabled:text-slate-400',
  ghost: 'bg-transparent text-slate-600 hover:bg-slate-100 disabled:text-slate-300',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
  inverse: 'bg-white text-brand-800 hover:bg-slate-50 disabled:bg-white/70',
  'inverse-outline': 'bg-transparent text-white ring-1 ring-inset ring-white/40 hover:bg-white/10',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm rounded-lg gap-1.5',
  md: 'px-4 py-2.5 text-sm rounded-xl gap-2',
  lg: 'px-6 py-3 text-[0.95rem] rounded-xl gap-2',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  isLoading = false,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center font-semibold transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100 ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...rest}
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
      )}
      {children}
    </button>
  )
}
