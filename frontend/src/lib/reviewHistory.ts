const HISTORY_STORAGE_KEY = 'reviewHistory'

function normalizeOwnerKey(ownerKey?: string | null) {
  const normalized = ownerKey?.trim().toLowerCase()
  return normalized ? normalized : null
}

function buildScopedHistoryStorageKey(ownerKey?: string | null) {
  const normalizedOwnerKey = normalizeOwnerKey(ownerKey)
  return normalizedOwnerKey ? `${HISTORY_STORAGE_KEY}:${normalizedOwnerKey}` : HISTORY_STORAGE_KEY
}

function getLocalStorageSafe() {
  if (typeof window === 'undefined') return null

  try {
    return window.localStorage
  } catch {
    return null
  }
}

function getSessionStorageSafe() {
  if (typeof window === 'undefined') return null

  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function parseStoredEntries<T>(rawValue: string | null): T[] | null {
  if (!rawValue) return null

  try {
    const parsed = JSON.parse(rawValue)
    return Array.isArray(parsed) ? parsed as T[] : null
  } catch {
    return null
  }
}

export function loadPersistedReviewHistory<T = unknown>(ownerKey?: string | null): T[] {
  const storageKey = buildScopedHistoryStorageKey(ownerKey)
  const localStorageRef = getLocalStorageSafe()
  const localEntries = parseStoredEntries<T>(localStorageRef?.getItem(storageKey) ?? null)

  if (localEntries) {
    return localEntries
  }

  if (normalizeOwnerKey(ownerKey)) {
    return []
  }

  const sessionStorageRef = getSessionStorageSafe()
  const legacyEntries = parseStoredEntries<T>(sessionStorageRef?.getItem(HISTORY_STORAGE_KEY) ?? null)

  if (!legacyEntries) {
    return []
  }

  if (localStorageRef) {
    try {
      localStorageRef.setItem(HISTORY_STORAGE_KEY, JSON.stringify(legacyEntries))
      sessionStorageRef?.removeItem(HISTORY_STORAGE_KEY)
    } catch {
      // Keep using the legacy session copy when localStorage writes fail.
    }
  }

  return legacyEntries
}

export function savePersistedReviewHistory<T>(entries: T[], ownerKey?: string | null) {
  const storageKey = buildScopedHistoryStorageKey(ownerKey)
  const serializedEntries = JSON.stringify(entries)
  const localStorageRef = getLocalStorageSafe()

  if (localStorageRef) {
    try {
      localStorageRef.setItem(storageKey, serializedEntries)
      getSessionStorageSafe()?.removeItem(storageKey)
      if (storageKey !== HISTORY_STORAGE_KEY) {
        getSessionStorageSafe()?.removeItem(HISTORY_STORAGE_KEY)
      }
      return
    } catch {
      // Fall through to sessionStorage if localStorage is unavailable.
    }
  }

  getSessionStorageSafe()?.setItem(storageKey, serializedEntries)
}
