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

/**
 * Safely parse JSON response with proper error handling.
 * Returns null if response is empty.
 */
export async function safeFetchJSON<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(url, options)

  // Check if response is OK
  if (!response.ok) {
    const text = await response.text().catch(() => '')

    // Try to extract backend error message from JSON body first
    let backendError: string | undefined
    try {
      const json = JSON.parse(text)
      backendError = json?.error || json?.detail || undefined
    } catch {
      // not JSON, use fallback messages below
    }

    if (backendError) {
      throw new APIError(backendError, response.status, text)
    }

    // Handle common HTTP errors with friendly messages
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new APIError('服务器暂时不可用，请稍后重试', response.status, text)
    }
    if (response.status === 401) {
      throw new APIError('登录已过期，请重新登录', response.status, text)
    }
    if (response.status === 403) {
      throw new APIError('没有权限执行此操作', response.status, text)
    }
    if (response.status === 404) {
      throw new APIError('请求的资源不存在', response.status, text)
    }
    if (response.status === 413) {
      throw new APIError('文件过大，请压缩后重试', response.status, text)
    }
    if (response.status === 429) {
      throw new APIError('请求过于频繁，请稍后再试', response.status, text)
    }
    if (response.status >= 500) {
      throw new APIError('服务器内部错误，请稍后重试', response.status, text)
    }

    throw new APIError(`请求失败 (${response.status})`, response.status, text)
  }

  // Check Content-Type
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()

  // If response is HTML (usually error page), throw error
  if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
    throw new APIError(
      '服务器返回了错误页面，请稍后重试',
      response.status,
      text.slice(0, 200)
    )
  }

  // If not JSON and not empty, throw error
  if (!contentType.includes('application/json') && text.trim()) {
    throw new APIError(
      '服务器返回了意外的格式，请稍后重试',
      response.status,
      text.slice(0, 200)
    )
  }

  // Empty response
  if (!text.trim()) {
    throw new APIError('服务器返回了空响应', response.status)
  }

  // Parse JSON
  try {
    return JSON.parse(text) as T
  } catch (error) {
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
