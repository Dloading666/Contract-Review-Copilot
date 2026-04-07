import { useState, useRef } from 'react'
import type { ReviewState } from '../App'
import mammoth from 'mammoth'

interface DocPanelProps {
  review: ReviewState
  onFileUpload: (text: string, filename: string) => void
}

export function DocPanel({ review, onFileUpload }: DocPanelProps) {
  const [zoom, setZoom] = useState(100)

  const isEmpty = review.status === 'idle'
  const contractText = review.contractText

  return (
    <section className="doc-panel">
      {/* Toolbar */}
      <div className="doc-panel__toolbar">
        <div className="doc-panel__toolbar-left">
          <span className="material-symbols-outlined doc-panel__toolbar-icon">menu</span>
          <h3 className="doc-panel__filename">
            {review.filename || '等待上传合同'}
          </h3>
        </div>
        <div className="doc-panel__toolbar-right">
          {!isEmpty && (
            <>
              <div className="doc-panel__zoom">
                <button className="doc-panel__zoom-btn" onClick={() => setZoom(z => Math.max(50, z - 10))}>
                  <span className="material-symbols-outlined">zoom_out</span>
                </button>
                <span className="doc-panel__zoom-level">{zoom}%</span>
                <button className="doc-panel__zoom-btn" onClick={() => setZoom(z => Math.min(200, z + 10))}>
                  <span className="material-symbols-outlined">zoom_in</span>
                </button>
              </div>
              <span className="material-symbols-outlined doc-panel__toolbar-icon">print</span>
              <span className="material-symbols-outlined doc-panel__toolbar-icon">download</span>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="doc-panel__content">
        {isEmpty ? (
          <UploadArea onFileUpload={onFileUpload} />
        ) : (
          <div
            className="doc-paper"
            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}
          >
            {/* Contract text rendered as-is */}
            <div className="doc-paper__contract-text">
              {contractText.split('\n').map((line, i) => {
                if (!line.trim()) return <br key={i} />
                // Try to detect clause headers
                if (/^第[一二三四五六七八九十]+条/.test(line.trim()) || /^[一二三四五六七八九十]+、/.test(line.trim())) {
                  return <h4 key={i} className="doc-paper__clause-title">{line}</h4>
                }
                if (/^(甲方|乙方|出租方|承租方)/.test(line.trim())) {
                  return <p key={i} className="doc-paper__party-line">{line}</p>
                }
                return <p key={i}>{line}</p>
              })}
            </div>

            {/* Watermark */}
            <div className="doc-paper__watermark">
              <span className="doc-paper__watermark-text">CONFIDENTIAL LEGAL DOCUMENT</span>
              <span className="doc-paper__watermark-text" style={{ top: '65%' }}>CONFIDENTIAL LEGAL DOCUMENT</span>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      {!isEmpty && (
        <div className="doc-panel__footer">
          <div className="doc-panel__footer-left">
            <span>字数: {contractText.length.toLocaleString()}</span>
          </div>
          <div className="doc-panel__footer-right">
            <div className="doc-panel__footer-status">
              <span className="doc-panel__footer-dot" />
              <span>已加密</span>
            </div>
            <span>智审内核 V4.2.0</span>
          </div>
        </div>
      )}
    </section>
  )
}

interface UploadAreaProps {
  onFileUpload: (text: string, filename: string) => void
}

function UploadArea({ onFileUpload }: UploadAreaProps) {
  const hiddenFileInput = useRef<HTMLInputElement>(null)

  const handleUploadClick = () => {
    hiddenFileInput.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const filename = file.name
    const ext = filename.split('.').pop()?.toLowerCase()

    try {
      let text = ''

      if (ext === 'txt') {
        text = await file.text()
      } else if (ext === 'docx') {
        const arrayBuffer = await file.arrayBuffer()
        const result = await mammoth.extractRawText({ arrayBuffer })
        text = result.value
      } else if (ext === 'pdf') {
        // PDF parsing in browser requires pdf.js — show a clear message
        alert('PDF 格式暂不支持，请将合同另存为 .docx 或 .txt 格式后上传。')
        return
      } else {
        text = await file.text()
      }

      if (text.trim().length < 10) {
        alert('合同内容为空或过短，请检查文件是否正确。')
        return
      }

      onFileUpload(text, filename)
    } catch (err) {
      console.error('File read error:', err)
      alert('文件读取失败，请尝试将合同另存为 .txt 格式后重新上传。')
    }

    // Reset input so the same file can be re-uploaded
    e.target.value = ''
  }

  return (
    <div className="upload-area">
      <div className="upload-area__icon">
        <span className="material-symbols-outlined" style={{ fontSize: 64, opacity: 0.5 }}>description</span>
      </div>
      <h2 className="upload-area__title">上传合同文档</h2>
      <p className="upload-area__desc">
        支持 .txt, .docx 格式的合同文件<br />
        系统将自动分析合同中的潜在风险条款
      </p>
      <div className="upload-area__actions">
        <button className="upload-area__btn upload-area__btn--primary" onClick={handleUploadClick}>
          <span className="material-symbols-outlined">upload</span>
          选择文件
        </button>
        <button className="upload-area__btn upload-area__btn--secondary">
          <span className="material-symbols-outlined">demo</span>
          查看示例
        </button>
      </div>
      <input
        ref={hiddenFileInput}
        type="file"
        accept=".txt,.docx,.doc"
        className="upload-area__input"
        onChange={handleFileChange}
      />
    </div>
  )
}
