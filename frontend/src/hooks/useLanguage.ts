import { useCallback, useEffect, useState } from 'react'
import { getPreferences, updatePreferences } from '../services/api'
import type { Language } from '../types'

const STORAGE_KEY = 'bis-sahayak-language'

export const languageOptions: { code: Language; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'bn', label: 'বাংলা' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'te', label: 'తెలుగు' },
  { code: 'mr', label: 'मराठी' },
  { code: 'gu', label: 'ગુજરાતી' },
  { code: 'kn', label: 'ಕನ್ನಡ' },
]

/**
 * Language preference is now persisted server-side via GET/PUT
 * /api/preferences (Phase 2). localStorage is kept only as an instant,
 * offline-friendly initial value so the UI doesn't flash to the default
 * while the backend request is in flight — the backend is the source of
 * truth once it responds.
 */
export function useLanguage() {
  const [language, setLanguageState] = useState<Language>(() => {
    if (typeof window === 'undefined') return 'en'
    return (window.localStorage.getItem(STORAGE_KEY) as Language | null) ?? 'en'
  })

  useEffect(() => {
    getPreferences()
      .then((prefs) => {
        setLanguageState(prefs.language as Language)
        window.localStorage.setItem(STORAGE_KEY, prefs.language)
      })
      .catch(() => {
        // Backend unreachable — keep the localStorage/default value already set.
      })
  }, [])

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next)
    window.localStorage.setItem(STORAGE_KEY, next)
    updatePreferences(next).catch(() => {
      // Backend unreachable — the UI already reflects the change locally;
      // it will sync again next time getPreferences() succeeds.
    })
  }, [])

  return { language, setLanguage }
}
