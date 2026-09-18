import { ShieldCheck, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { navItems } from './navItems'

interface SidebarProps {
  open: boolean
  onClose: () => void
}

// Tailwind needs literal class strings present in source to include them
// in the compiled CSS — a template string like `bg-${color}-100` would
// silently produce no styles at all. This map is the static equivalent.
// Each section keeps its own color (explicit direction: "add color to
// icons"), but tuned toward richer/deeper tones on hover+active rather
// than flat pastel fills — flat single-tone badges read templated; a
// slight depth cue (soft tint at rest, a solid deep fill only once
// active) reads more considered.
const ICON_BADGE_CLASSES: Record<string, { inactive: string; active: string }> = {
  slate: { inactive: 'bg-slate-100 text-slate-500', active: 'bg-slate-800 text-white' },
  emerald: { inactive: 'bg-emerald-50 text-emerald-600', active: 'bg-emerald-600 text-white' },
  sky: { inactive: 'bg-sky-50 text-sky-600', active: 'bg-sky-600 text-white' },
  violet: { inactive: 'bg-violet-50 text-violet-600', active: 'bg-violet-600 text-white' },
  amber: { inactive: 'bg-amber-50 text-amber-700', active: 'bg-amber-500 text-white' },
  rose: { inactive: 'bg-rose-50 text-rose-600', active: 'bg-rose-600 text-white' },
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      {open && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-[2px] lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-200/80 bg-white transition-transform lg:static lg:z-0 lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-700 to-brand-900 text-white shadow-[var(--shadow-sm)]">
              <ShieldCheck size={17} strokeWidth={2.25} />
            </div>
            <div className="leading-none">
              <p className="text-[14px] font-bold tracking-tight text-slate-900">BIS Sahayak</p>
              <p className="mt-1 text-[11px] text-slate-500">Standards Assistant</p>
            </div>
          </div>
          <button
            aria-label="Close navigation"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-3" aria-label="Primary">
          {navItems.map((item) => {
            const colors = ICON_BADGE_CLASSES[item.color] ?? ICON_BADGE_CLASSES.slate
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={onClose}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-xl px-2.5 py-2 text-[13.5px] font-medium transition-all ${
                    isActive ? 'bg-slate-100/80 text-slate-900' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
                        isActive ? colors.active : `${colors.inactive} group-hover:scale-105`
                      }`}
                    >
                      <item.icon size={16} strokeWidth={2.25} />
                    </span>
                    {item.label}
                  </>
                )}
              </NavLink>
            )
          })}
        </nav>

        <div className="border-t border-slate-100 px-4 py-3.5">
          <p className="text-[11px] leading-relaxed text-slate-500">
            SIH26107 &middot; Ministry of Consumer Affairs,
            <br />
            Food &amp; Public Distribution (BIS)
          </p>
        </div>
      </aside>
    </>
  )
}
