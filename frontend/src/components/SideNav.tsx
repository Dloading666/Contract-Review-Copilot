interface SideNavProps {
  activeItem?: 'chat' | 'risks' | 'laws' | 'compare'
}

export function SideNav({ activeItem = 'chat' }: SideNavProps) {
  const items = [
    { id: 'chat' as const, icon: 'chat_bubble', label: '实时对话' },
    { id: 'risks' as const, icon: 'warning', label: '风险清单' },
    { id: 'laws' as const, icon: 'gavel', label: '法律依据' },
    { id: 'compare' as const, icon: 'difference', label: '版本对比' },
  ]

  return (
    <aside className="side-nav">
      <div className="side-nav__items">
        {items.map((item) => (
          <a
            key={item.id}
            href="#"
            className={`side-nav__item ${activeItem === item.id ? 'side-nav__item--active' : ''}`}
          >
            <span className="material-symbols-outlined side-nav__item-icon">{item.icon}</span>
            <span className="side-nav__item-label">{item.label}</span>
          </a>
        ))}
      </div>
      <div className="side-nav__footer">
        <a href="#" className="side-nav__item">
          <span className="material-symbols-outlined side-nav__item-icon">help</span>
        </a>
        <a href="#" className="side-nav__item">
          <span className="material-symbols-outlined side-nav__item-icon">feedback</span>
        </a>
      </div>
    </aside>
  )
}
