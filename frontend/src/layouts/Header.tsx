import { Globe, Menu } from 'lucide-react'
import { useState } from 'react'
import { languageOptions, useLanguage } from '../hooks/useLanguage'
import { AccountMenu } from './AccountMenu'

interface HeaderProps {
  onMenuClick: () => void
  title: string
}

export function Header({ onMenuClick, title }: HeaderProps) {
  const { language, setLanguage } = useLanguage()
  const [langOpen, setLangOpen] = useState(false)

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/80 px-4 backdrop-blur-md sm:px-6">
      <div className="flex items-center gap-3">
        <button
          aria-label="Open navigation"
          className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden"
          onClick={onMenuClick}
        >
          <Menu size={20} />
        </button>
        <h1 className="text-[15px] font-semibold tracking-tight text-slate-900">{title}</h1>
      </div>

      <div className="relative">
        <button
          onClick={() => setLangOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={langOpen}
          className="flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1.5 text-[13px] font-medium text-slate-600 hover:bg-slate-50"
        >
          <Globe size={14.5} />
          <span className="hidden sm:inline">{languageOptions.find((l) => l.code === language)?.label}</span>
        </button>
        {langOpen && (
          <>
            <button
              aria-hidden="true"
              tabIndex={-1}
              className="fixed inset-0 z-10 cursor-default"
              onClick={() => setLangOpen(false)}
            />
            <ul
              role="listbox"
              className="absolute right-0 z-20 mt-2 w-40 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-[var(--shadow-lg)]"
            >
              {languageOptions.map((opt) => (
                <li key={opt.code}>
                  <button
                    role="option"
                    aria-selected={opt.code === language}
                    className={`flex w-full items-center px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                      opt.code === language ? 'font-semibold text-accent-700' : 'text-slate-600'
                    }`}
                    onClick={() => {
                      setLanguage(opt.code)
                      setLangOpen(false)
                    }}
                  >
                    {opt.label}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="ml-2">
        <AccountMenu />
      </div>
    </header>
  )
}
