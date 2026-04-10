import { useEffect, useRef, useState } from 'react'
import { MessageSquare, History, Settings } from 'lucide-react'
import { loadPersistedReviewHistoryFromOwners } from '../lib/reviewHistory'
import type { User } from '../contexts/AuthContext'

interface SideNavProps {
  user?: User | null
  onLogout?: () => void
  onSelectHistorySession?: (sessionId: string) => void
  onOpenSettings?: () => void
  activeView?: string
}

interface HistoryListItem {
  sessionId: string
  filename: string
  date: string
}

export function SideNav({ user, onLogout, onSelectHistorySession, onOpenSettings, activeView }: SideNavProps) {
  const [showHistory, setShowHistory] = useState(false)
  const [historyItems, setHistoryItems] = useState<HistoryListItem[]>([])
  const historyDropdownRef = useRef<HTMLDivElement>(null)
  const historyButtonRef = useRef<HTMLButtonElement>(null)

  const loadHistoryItems = () => {
    try {
      const parsed = loadPersistedReviewHistoryFromOwners<HistoryListItem>([user?.id, user?.email])
      setHistoryItems(parsed)
    } catch {
      setHistoryItems([])
    }
  }

  const handleHistoryClick = () => {
    loadHistoryItems()
    setShowHistory(prev => !prev)
  }

  const handleHistorySelect = (sessionId: string) => {
    setShowHistory(false)
    onSelectHistorySession?.(sessionId)
  }

  useEffect(() => {
    if (!showHistory) return
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (historyDropdownRef.current?.contains(target)) return
      if (historyButtonRef.current?.contains(target)) return
      setShowHistory(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showHistory])

  const navItems = [
    { id: 'chat', icon: <MessageSquare size={26} />, label: '实时对话', onClick: () => setShowHistory(false) },
    { id: 'history', icon: <History size={26} />, label: '审查历史', onClick: handleHistoryClick, ref: historyButtonRef },
  ]

  return (
    <aside style={{
      width: 112,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--color-cream-dark)',
      borderRight: '4px solid black',
      overflow: 'visible',
      position: 'relative',
    }}>
      {/* Doge logo strip */}
      <div style={{ padding: 8, borderBottom: '4px solid black' }}>
        <div style={{
          border: '3px solid black',
          background: 'white',
          padding: '7px 4px',
          textAlign: 'center',
          fontFamily: 'var(--font-header)',
          fontSize: 7,
          lineHeight: 1.5,
          color: 'var(--color-ink)',
          overflow: 'hidden',
        }}>
          合规智审<br />Copilot
        </div>
      </div>

      {/* Doge avatar with ONLINE badge */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 8px', borderBottom: '4px solid black', background: 'var(--color-paper)' }}>
        <div style={{ position: 'relative' }}>
          <img
            src="/doge.png"
            alt="Doge"
            style={{
              width: 56,
              height: 56,
              border: '3px solid black',
              objectFit: 'contain',
              imageRendering: 'pixelated',
              background: 'white',
            }}
          />
          <div style={{
            position: 'absolute',
            bottom: -4,
            right: -4,
            background: 'var(--color-green)',
            border: '2px solid black',
            padding: '1px 4px',
            fontFamily: 'var(--font-pixel)',
            fontSize: 6,
            fontWeight: 700,
            color: 'white',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            whiteSpace: 'nowrap',
          }}>
            ONLINE
          </div>
        </div>
      </div>

      {/* Nav items */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {navItems.map(item => {
          const button = (
            <button
              ref={item.ref as any}
              type="button"
              className={`pixel-sidebar-btn${activeView === item.id || (item.id === 'history' && showHistory) ? ' active' : ''}`}
              onClick={item.onClick}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          )

          if (item.id !== 'history') {
            return <div key={item.id}>{button}</div>
          }

          return (
            <div key={item.id} style={{ position: 'relative', overflow: 'visible' }}>
              {button}
              {showHistory && (
                <div
                  ref={historyDropdownRef}
                  style={{
                    position: 'absolute',
                    left: 'calc(100% + 8px)',
                    top: 0,
                    width: 280,
                    background: 'var(--color-paper)',
                    border: '4px solid black',
                    boxShadow: '6px 6px 0 rgba(0,0,0,1)',
                    zIndex: 200,
                    maxHeight: 400,
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  <div style={{
                    padding: '10px 14px',
                    background: 'var(--color-orange)',
                    color: 'white',
                    fontFamily: 'var(--font-pixel)',
                    fontSize: 9,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    borderBottom: '4px solid black',
                    flexShrink: 0,
                  }}>
                    审查历史
                  </div>
                  {historyItems.length === 0 ? (
                    <div style={{ padding: '24px 14px', textAlign: 'center', fontFamily: 'var(--font-pixel)', fontSize: 8, color: 'var(--color-ink-muted)' }}>
                      暂无历史记录
                    </div>
                  ) : (
                    <div style={{ overflowY: 'auto', flex: 1 }}>
                      {historyItems.map(historyItem => (
                        <button
                          key={historyItem.sessionId}
                          type="button"
                          onClick={() => handleHistorySelect(historyItem.sessionId)}
                          style={{
                            display: 'block',
                            width: '100%',
                            textAlign: 'left',
                            padding: '10px 14px',
                            border: 'none',
                            borderBottom: '3px solid black',
                            background: 'white',
                            cursor: 'pointer',
                            fontFamily: 'var(--font-pixel)',
                            fontSize: 8,
                            color: 'var(--color-ink)',
                          }}
                          onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-orange-light)')}
                          onMouseLeave={e => (e.currentTarget.style.background = 'white')}
                        >
                          <div style={{ fontWeight: 700, marginBottom: 4, lineHeight: 1.4 }}>{historyItem.filename}</div>
                          <div style={{ fontSize: 7, color: 'var(--color-ink-muted)' }}>{historyItem.date}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer: settings + logout */}
      <div style={{ borderTop: '4px solid black' }}>
        {user?.email && (
          <div style={{
            padding: '8px 8px',
            fontFamily: 'var(--font-pixel)',
            fontSize: 9,
            wordBreak: 'break-all',
            textAlign: 'center',
            background: 'white',
            borderBottom: '4px solid black',
            color: 'var(--color-ink-soft)',
            lineHeight: 1.6,
          }}>
            {user.email}
          </div>
        )}
        <button
          type="button"
          className={`pixel-sidebar-btn${activeView === 'settings' ? ' active' : ''}`}
          style={{ borderTop: 'none', borderBottom: 'none' }}
          onClick={onOpenSettings}
        >
          <Settings size={26} />
          <span>系统设置</span>
        </button>
        <button
          type="button"
          onClick={onLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            width: '100%',
            padding: '10px 8px',
            border: 'none',
            borderTop: '4px solid black',
            background: 'var(--color-paper)',
            color: 'var(--color-red)',
            fontFamily: 'var(--font-pixel)',
            fontSize: 10,
            fontWeight: 700,
            textTransform: 'uppercase',
            cursor: 'pointer',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-red-light)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--color-paper)')}
        >
          退出登录
        </button>
      </div>

    </aside>
  )
}
