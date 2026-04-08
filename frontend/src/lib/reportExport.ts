function buildFallbackName(filename?: string) {
  const sourceName = (filename || '').replace(/\.[^.]+$/, '').trim()
  const date = new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')
  return `${sourceName || '避坑指南'}_${date}.docx`
}

export async function exportReportAsWord(params: {
  filename?: string
  reportParagraphs: string[]
  token?: string | null
}) {
  const response = await fetch('/api/review/export-docx', {
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
    const errorText = await response.text()
    throw new Error(errorText || `Export failed with status ${response.status}`)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = buildFallbackName(params.filename)
  anchor.click()
  URL.revokeObjectURL(url)
}
