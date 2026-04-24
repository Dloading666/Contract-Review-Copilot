const PRODUCTION_GATEWAY_HOSTS = new Set(['ctsafe.top', 'www.ctsafe.top'])

function normalizeBasePath(path: string) {
  const trimmed = path.trim()
  if (!trimmed) return '/api'
  const withLeadingSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  return withLeadingSlash.replace(/\/+$/, '') || '/api'
}

function detectBasePath() {
  const configured = import.meta.env.VITE_API_BASE_PATH
  if (configured) {
    return normalizeBasePath(configured)
  }

  const hostname = typeof window !== 'undefined' ? window.location.hostname : ''
  return PRODUCTION_GATEWAY_HOSTS.has(hostname) ? '/gateway' : '/api'
}

export const API_BASE_PATH = detectBasePath()

export function apiPath(path: string) {
  if (/^https?:\/\//i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_PATH}${normalizedPath}`
}
