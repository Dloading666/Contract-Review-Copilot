/**
 * Safe fetch wrapper that handles non-JSON responses and provides friendly error messages.
 */

export class APIError extends Error {
  constructor(
    message: string,
    public status?: number,
    public responseText?: string
  ) {
    super(message)
    this.name = 'APIError'
  }
}

export function isHTMLResponseText(text: string): boolean {
  const trimmed = text.trim()
  return trimmed.startsWith('<!DOCTYPE') || trimmed.startsWith('<html')
}

export function isCloudflareChallengeText(text: string): boolean {
  const normalized = text.toLowerCase()
  return normalized.includes('just a moment') || normalized.includes('cloudflare')
}

export function getGatewayErrorMessage(status?: number, responseText = ''): string {
  if (isCloudflareChallengeText(responseText)) {
    return '站点防护拦截了接口请求，请稍后重试或联系管理员检查 Cloudflare 规则'
  }

  if (status === 401) {
    return '登录已过期，请重新登录'
  }
  if (status === 502 || status === 503 || status === 504) {
    return '服务暂时不可用，请稍后重试'
  }
  if (status === 403) {
    return '没有权限执行此操作'
  }
  if (status === 404) {
    return '请求的资源不存在'
  }
  if (status === 413) {
    return '文件过大，请压缩后重试'
  }
  if (status === 429) {
    return '请求过于频繁，请稍后再试'
  }
  if (typeof status === 'number' && status >= 500) {
    return '服务器内部错误，请稍后重试'
  }
  if (isHTMLResponseText(responseText)) {
    return '服务器返回了错误页面，请稍后重试'
  }
  return typeof status === 'number' ? `请求失败 (${status})` : '请求失败，请稍后重试'
}

function isSessionAuthError(message: string): boolean {
  const normalized = message.trim().toLowerCase()
  return (
    !normalized ||
    normalized.includes('unauthorized') ||
    normalized.includes('not authenticated') ||
    normalized.includes('invalid token') ||
    normalized.includes('token expired') ||
    normalized.includes('未登录') ||
    normalized.includes('登录已过期') ||
    normalized.includes('请重新登录')
  )
}

/**
 * Safely parse JSON response with proper error handling.
 * Returns null if response is empty.
 */
export async function safeFetchJSON<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, options)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error
    }

    const message = error instanceof Error && /failed to fetch/i.test(error.message)
      ? '网络请求没有到达服务端，请检查网络或站点网关设置后重试'
      : '请求发送失败，请稍后重试'
    throw new APIError(message)
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '')

    let backendError: string | undefined
    try {
      const json = JSON.parse(text)
      backendError = json?.error || json?.detail || undefined
    } catch {
      // Ignore invalid JSON error bodies and fall back to status-based messaging.
    }

    if (response.status === 401) {
      const message = backendError && !isSessionAuthError(backendError)
        ? backendError
        : getGatewayErrorMessage(response.status, text)
      throw new APIError(message, response.status, text)
    }

    if (backendError) {
      throw new APIError(backendError, response.status, text)
    }

    throw new APIError(getGatewayErrorMessage(response.status, text), response.status, text)
  }

  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()

  if (isHTMLResponseText(text)) {
    throw new APIError(
      getGatewayErrorMessage(response.status, text),
      response.status,
      text.slice(0, 200)
    )
  }

  if (!contentType.includes('application/json') && text.trim()) {
    throw new APIError(
      '服务器返回了意外的格式，请稍后重试',
      response.status,
      text.slice(0, 200)
    )
  }

  if (!text.trim()) {
    throw new APIError('服务器返回了空响应', response.status)
  }

  try {
    return JSON.parse(text) as T
  } catch {
    throw new APIError(
      '服务器返回了无效的数据格式',
      response.status,
      text.slice(0, 200)
    )
  }
}

/**
 * Post JSON data with proper error handling.
 */
export async function postJSON<T>(
  url: string,
  body: object,
  options?: RequestInit
): Promise<T> {
  return safeFetchJSON<T>(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    body: JSON.stringify(body),
    ...options,
  })
}
