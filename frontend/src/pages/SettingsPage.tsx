import { Globe, Settings as SettingsIcon } from 'lucide-react'
import { Card } from '../components/ui'
import { languageOptions, useLanguage } from '../hooks/useLanguage'

export function SettingsPage() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
          <SettingsIcon size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Settings</h1>
          <p className="mt-0.5 text-sm text-slate-500">Manage your assistant preferences.</p>
        </div>
      </div>

      <Card className="p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600">
            <Globe size={18} />
          </div>
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-slate-900">Preferred language</h2>
            <p className="mt-1 text-sm text-slate-500">
              Choose the language you would like the assistant to respond in.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {languageOptions.map((opt) => (
                <button
                  key={opt.code}
                  onClick={() => setLanguage(opt.code)}
                  className={`rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${
                    opt.code === language
                      ? 'border-accent-300 bg-accent-50 text-accent-700'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}
