import { FileDown, FilePlus } from 'lucide-react'

interface TopNavProps {
  onNewReview?: () => void
  onExportReport?: () => void
}

export function TopNav({ onNewReview, onExportReport }: TopNavProps) {
  const handleExportReport = () => {
    if (onExportReport) { onExportReport(); return }
    const reportData = sessionStorage.getItem('lastReport')
    if (!reportData) return
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
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className="top-nav__logo-box">
          <div className="top-nav__logo-diamond" />
        </div>
        <div className="top-nav__title">
          合规智审<br />Copilot
        </div>
      </div>

      {/* Actions */}
      <div className="top-nav__actions">
        <button
          className="px-btn px-btn--ghost"
          onClick={handleExportReport}
        >
          <FileDown size={14} />
          导出报告
        </button>
        <button
          className="px-btn px-btn--orange"
          onClick={onNewReview}
        >
          <FilePlus size={14} />
          新建审查
        </button>
      </div>
    </header>
  )
}
