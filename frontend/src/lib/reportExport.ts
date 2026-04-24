import { getGatewayErrorMessage, isHTMLResponseText } from './apiClient'
import { apiPath } from './apiPaths'

function buildFallbackName(filename?: string) {
  const sourceName = (filename || '').replace(/\.[^.]+$/, '').trim()
  const date = new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')
  return `${sourceName || '避坑指南'}_${date}.docx`
}

function getFriendlyErrorMessage(status: number, text: string): string {
  if (status === 502 || status === 503 || status === 504) {
    return '服务暂时不可用，请稍后重试'
  }
  if (status === 401) {
    return '登录已过期，请重新登录'
  }
  if (status === 413) {
    return '报告内容过大，请减少内容后重试'
  }
  if (status === 429) {
    return '请求过于频繁，请稍后再试'
  }
  if (status >= 500) {
    return '服务器内部错误，请稍后重试'
  }
  if (isHTMLResponseText(text)) {
    return getGatewayErrorMessage(status, text)
  }
  return text || `导出失败 (${status})`
}

export async function exportReportAsWord(params: {
  filename?: string
  reportParagraphs: string[]
  token?: string | null
}) {
  const response = await fetch(apiPath('/review/export-docx'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(params.token ? { Authorization: `Bearer ${params.token}` } : {}),
    },
    body: JSON.stringify({
      filename: params.filename,
      report_paragraphs: params.reportParagraphs,
    }),
  })

  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(getFriendlyErrorMessage(response.status, errorText))
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = buildFallbackName(params.filename)
  anchor.click()
  URL.revokeObjectURL(url)
}
