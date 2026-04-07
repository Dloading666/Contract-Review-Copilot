import { useEffect, useRef, useState } from 'react'

interface HistoryListItem {
  sessionId: string
  filename: string
  date: string
}

interface SideNavProps {
  user?: { email: string; id: string } | null
  onLogout?: () => void
  onSelectHistorySession?: (sessionId: string) => void
}

const HISTORY_STORAGE_KEY = 'reviewHistory'

export function SideNav({
  user,
  onLogout,
  onSelectHistorySession,
}: SideNavProps) {
  const [showHistory, setShowHistory] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [historyItems, setHistoryItems] = useState<HistoryListItem[]>([])
  const historyDropdownRef = useRef<HTMLDivElement>(null)
  const settingsDropdownRef = useRef<HTMLDivElement>(null)
  const historyButtonRef = useRef<HTMLButtonElement>(null)
  const settingsButtonRef = useRef<HTMLButtonElement>(null)

  const loadHistoryItems = () => {
    try {
      const saved = sessionStorage.getItem(HISTORY_STORAGE_KEY)
      const parsed = saved ? JSON.parse(saved) : []
      setHistoryItems(Array.isArray(parsed) ? parsed : [])
    } catch {
      setHistoryItems([])
    }
  }

  const handleChatClick = () => {
    setShowHistory(false)
    setShowSettings(false)
  }

  const handleHistoryClick = () => {
    loadHistoryItems()
    setShowSettings(false)
    setShowHistory((prev) => !prev)
  }

  const handleHistorySelect = (sessionId: string) => {
    setShowHistory(false)
    onSelectHistorySession?.(sessionId)
  }

  const handleSettingsClick = () => {
    setShowHistory(false)
    setShowSettings((prev) => !prev)
  }

  const handleLogoutClick = () => {
    setShowSettings(false)
    onLogout?.()
  }

  useEffect(() => {
    if (!showHistory && !showSettings) {
      return
    }

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (historyDropdownRef.current?.contains(target)) return
      if (historyButtonRef.current?.contains(target)) return
      if (settingsDropdownRef.current?.contains(target)) return
      if (settingsButtonRef.current?.contains(target)) return

      setShowHistory(false)
      setShowSettings(false)
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showHistory, showSettings])

  return (
    <aside className="side-nav">
      <div className="side-nav__items">
        <button
          type="button"
          className={`side-nav__item ${!showHistory && !showSettings ? 'side-nav__item--active' : ''}`}
          onClick={handleChatClick}
        >
          <span className="material-symbols-outlined side-nav__item-icon">chat_bubble</span>
          <span className="side-nav__item-label">实时对话</span>
        </button>
        <button
          ref={historyButtonRef}
          type="button"
          className={`side-nav__item ${showHistory ? 'side-nav__item--active' : ''}`}
          onClick={handleHistoryClick}
        >
          <span className="material-symbols-outlined side-nav__item-icon">history</span>
          <span className="side-nav__item-label">对话历史</span>
        </button>
      </div>

      <div className="side-nav__footer">
        <button
          ref={settingsButtonRef}
          type="button"
          className={`side-nav__item ${showSettings ? 'side-nav__item--active' : ''}`}
          onClick={handleSettingsClick}
        >
          <span className="material-symbols-outlined side-nav__item-icon">settings</span>
          <span className="side-nav__item-label">设置</span>
        </button>
      </div>

      {showHistory && (
        <div className="side-nav__history-dropdown" ref={historyDropdownRef}>
          <div className="side-nav__history-header">审查历史</div>
          {historyItems.length === 0 ? (
            <div className="side-nav__history-empty">暂无历史记录</div>
          ) : (
            <div className="side-nav__history-list">
              {historyItems.map((item) => (
                <button
                  key={item.sessionId}
                  type="button"
                  className="side-nav__history-item"
                  onClick={() => handleHistorySelect(item.sessionId)}
                >
                  <div className="side-nav__history-filename">{item.filename}</div>
                  <div className="side-nav__history-date">{item.date}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {showSettings && (
        <div className="side-nav__settings-dropdown" ref={settingsDropdownRef}>
          <div className="side-nav__settings-header">设置</div>
          <div className="side-nav__settings-section">
            <div className="side-nav__settings-label">当前账号</div>
            <div className="side-nav__settings-email" title={user?.email ?? '未登录'}>
              {user?.email ?? '未登录'}
            </div>
          </div>
          <button
            type="button"
            className="side-nav__settings-logout"
            onClick={handleLogoutClick}
          >
            <span className="material-symbols-outlined">logout</span>
            退出登录
          </button>
        </div>
      )}
    </aside>
  )
}
