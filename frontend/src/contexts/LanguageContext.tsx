import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { type Language, type Translations, translations } from '../i18n/translations'

const STORAGE_KEY = 'crc_language'

function detectDefaultLanguage(): Language {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && stored in translations) return stored as Language
  return 'zh-CN'
}

interface LanguageContextValue {
  lang: Language
  tr: Translations
  setLanguage: (lang: Language) => void
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Language>(detectDefaultLanguage)

  const setLanguage = useCallback((next: Language) => {
    localStorage.setItem(STORAGE_KEY, next)
    setLang(next)
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  return (
    <LanguageContext.Provider value={{ lang, tr: translations[lang], setLanguage }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}

export function getCurrentTranslations(): Translations {
  const stored = localStorage.getItem(STORAGE_KEY)
  const lang: Language = (stored && stored in translations) ? stored as Language : 'zh-CN'
  return translations[lang]
}
