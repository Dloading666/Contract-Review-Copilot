interface TopNavProps {
  onNewReview?: () => void
  onExportReport?: () => void
}

export function TopNav({ onNewReview, onExportReport }: TopNavProps) {
  const handleExportReport = () => {
    if (onExportReport) {
      onExportReport()
      return
    }

    const reportData = sessionStorage.getItem('lastReport')
    if (!reportData) {
      return
    }

    const blob = new Blob([reportData], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `避坑指南_${new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <header className="top-nav">
      <div className="top-nav__brand">
        <div className="top-nav__logo">合规智审 Copilot</div>
      </div>
      <div className="top-nav__actions">
        <button className="top-nav__btn top-nav__btn--secondary" onClick={handleExportReport}>
          导出报告
        </button>
        <button className="top-nav__btn top-nav__btn--primary" onClick={onNewReview}>
          新建审查
        </button>
      </div>
    </header>
  )
}
