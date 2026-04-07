interface TopNavProps {
  user?: { email: string; id: string } | null
  onLogout?: () => void
}

export function TopNav({ user, onLogout }: TopNavProps) {
  return (
    <header className="top-nav">
      <div className="top-nav__brand">
        <div className="top-nav__logo">合规智审 Copilot</div>
        <nav className="top-nav__nav">
          <a className="top-nav__nav-item top-nav__nav-item--active" href="#">项目大厅</a>
          <a className="top-nav__nav-item" href="#">文档库</a>
          <a className="top-nav__nav-item" href="#">审查模板</a>
          <a className="top-nav__nav-item" href="#">合规看板</a>
        </nav>
      </div>
      <div className="top-nav__actions">
        <button className="top-nav__btn top-nav__btn--secondary">导出报告</button>
        <button className="top-nav__btn top-nav__btn--primary">新建审查</button>
        <div className="top-nav__divider" />
        <div className="top-nav__icons">
          <span className="material-symbols-outlined top-nav__icon">notifications</span>
          <span className="material-symbols-outlined top-nav__icon">history</span>
          <span className="material-symbols-outlined top-nav__icon">settings</span>
          {user ? (
            <div className="top-nav__user-menu">
              <span className="top-nav__user-email">{user.email}</span>
              <button className="top-nav__logout" onClick={onLogout}>
                <span className="material-symbols-outlined">logout</span>
                退出
              </button>
            </div>
          ) : (
            <img
              alt="用户头像"
              className="top-nav__avatar"
              src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop&crop=face"
            />
          )}
        </div>
      </div>
    </header>
  )
}
