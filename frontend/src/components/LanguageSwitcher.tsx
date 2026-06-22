import { useEffect, useRef, useState } from 'react'
import { Globe } from 'lucide-react'
import { ALL_LANGUAGES, LANGUAGE_NAMES, type Language } from '../i18n/translations'
import { useLanguage } from '../contexts/LanguageContext'

interface LanguageSwitcherProps {
  variant?: 'desktop' | 'mobile' | 'landing'
}

export function LanguageSwitcher({ variant = 'desktop' }: LanguageSwitcherProps) {
  const { lang, setLanguage, tr } = useLanguage()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const handleSelect = (selected: Language) => {
    setLanguage(selected)
    setOpen(false)
  }

  if (variant === 'landing') {
    return (
      <div ref={containerRef} style={{ position: 'relative' }}>
        <button
          type="button"
          className="brutalist-button landing-button landing-button--ghost"
          onClick={() => setOpen(prev => !prev)}
          aria-label={tr.nav.lang}
          title={tr.nav.lang}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
        >
          <Globe size={18} strokeWidth={3} />
          {LANGUAGE_NAMES[lang]}
        </button>

        {open && (
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: 180,
            background: '#f7f7f2',
            border: '3px solid #2d2f2c',
            boxShadow: '6px 6px 0 0 #11120f',
            zIndex: 1000,
          }}>
            {ALL_LANGUAGES.map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => handleSelect(l)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '11px 14px',
                  border: 'none',
                  borderBottom: '2px solid #2d2f2c',
                  background: l === lang ? '#6bfe9c' : 'transparent',
                  fontFamily: "'Work Sans', sans-serif",
                  fontSize: 14,
                  fontWeight: l === lang ? 700 : 500,
                  color: '#2d2f2c',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => { if (l !== lang) e.currentTarget.style.background = '#e8e9e3' }}
                onMouseLeave={e => { if (l !== lang) e.currentTarget.style.background = 'transparent' }}
              >
                {l === lang ? '✓ ' : ''}{LANGUAGE_NAMES[l]}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (variant === 'mobile') {
    return (
      <div ref={containerRef} style={{ position: 'relative', flex: 1, minWidth: 0, height: '100%' }}>
        <button
          type="button"
          className={`pixel-sidebar-btn${open ? ' active' : ''}`}
          onClick={() => setOpen(prev => !prev)}
          style={{ flex: 1, minWidth: 0, width: '100%', height: '100%', flexDirection: 'column', gap: 3, fontSize: 9, lineHeight: 1.2, padding: '4px 2px', borderTop: 'none', borderBottom: 'none', borderLeft: 'none', borderRight: '4px solid black' }}
          aria-label={tr.nav.lang}
          title={tr.nav.lang}
        >
          <Globe size={20} />
          <span style={{ fontSize: 8 }}>{LANGUAGE_NAMES[lang].slice(0, 2)}</span>
        </button>

        {open && (
          <div style={{
            position: 'fixed',
            bottom: 'calc(80px + env(safe-area-inset-bottom, 0px))',
            left: 8,
            right: 8,
            background: 'var(--color-paper)',
            border: '4px solid black',
            boxShadow: '0 6px 0 rgba(0,0,0,1)',
            zIndex: 500,
          }}>
            <div style={{
              padding: '8px 12px',
              background: 'var(--color-orange)',
              color: 'white',
              fontFamily: 'var(--font-pixel)',
              fontSize: 9,
              fontWeight: 700,
              textTransform: 'uppercase',
              borderBottom: '3px solid black',
            }}>
              {tr.nav.lang}
            </div>
            {ALL_LANGUAGES.map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => handleSelect(l)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '10px 14px',
                  border: 'none',
                  borderBottom: '3px solid black',
                  background: l === lang ? 'var(--color-orange-light)' : 'white',
                  fontFamily: 'var(--font-pixel)',
                  fontSize: 10,
                  fontWeight: l === lang ? 700 : 400,
                  color: 'var(--color-ink)',
                  cursor: 'pointer',
                }}
              >
                {l === lang ? '✓ ' : ''}{LANGUAGE_NAMES[l]}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div ref={containerRef} style={{ position: 'relative', overflow: 'visible' }}>
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        aria-label={tr.nav.lang}
        title={tr.nav.lang}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          padding: '18px 8px',
          width: '100%',
          aspectRatio: '1',
          border: 'none',
          background: open ? 'var(--color-orange)' : 'var(--color-paper)',
          color: open ? 'white' : 'var(--color-ink)',
          cursor: 'pointer',
          fontFamily: 'var(--font-pixel)',
          fontSize: 13,
          fontWeight: 700,
          textTransform: 'uppercase',
          textAlign: 'center',
          lineHeight: 1.4,
          transition: 'background 0.1s, color 0.1s',
        }}
        onMouseEnter={e => { if (!open) { e.currentTarget.style.background = 'var(--color-orange)'; e.currentTarget.style.color = 'white' } }}
        onMouseLeave={e => { if (!open) { e.currentTarget.style.background = 'var(--color-paper)'; e.currentTarget.style.color = 'var(--color-ink)' } }}
      >
        <Globe size={26} />
        <span>{LANGUAGE_NAMES[lang]}</span>
      </button>

      {open && (
        <div style={{
          position: 'absolute',
          bottom: 'calc(100% + 4px)',
          left: 0,
          width: 160,
          background: 'var(--color-paper)',
          border: '4px solid black',
          boxShadow: '6px 6px 0 rgba(0,0,0,1)',
          zIndex: 300,
        }}>
          <div style={{
            padding: '8px 12px',
            background: 'var(--color-orange)',
            color: 'white',
            fontFamily: 'var(--font-pixel)',
            fontSize: 9,
            fontWeight: 700,
            textTransform: 'uppercase',
            borderBottom: '3px solid black',
          }}>
            {tr.nav.lang}
          </div>
          {ALL_LANGUAGES.map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => handleSelect(l)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '9px 12px',
                border: 'none',
                borderBottom: '3px solid black',
                background: l === lang ? 'var(--color-orange-light)' : 'white',
                fontFamily: 'var(--font-pixel)',
                fontSize: 10,
                fontWeight: l === lang ? 700 : 400,
                color: 'var(--color-ink)',
                cursor: 'pointer',
              }}
              onMouseEnter={e => { if (l !== lang) e.currentTarget.style.background = 'var(--color-cream-dark)' }}
              onMouseLeave={e => { if (l !== lang) e.currentTarget.style.background = 'white' }}
            >
              {l === lang ? '✓ ' : ''}{LANGUAGE_NAMES[l]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
