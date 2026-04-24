import { getPersistentStoreSafe, getTransientStoreSafe } from './browserStorage'

const HISTORY_STORAGE_KEY = 'reviewHistory'

function normalizeOwnerKey(ownerKey?: string | null) {
  const normalized = ownerKey?.trim().toLowerCase()
  return normalized ? normalized : null
}

function buildScopedHistoryStorageKey(ownerKey?: string | null) {
  const normalizedOwnerKey = normalizeOwnerKey(ownerKey)
  return normalizedOwnerKey ? `${HISTORY_STORAGE_KEY}:${normalizedOwnerKey}` : HISTORY_STORAGE_KEY
}

function normalizeOwnerKeys(ownerKeys?: Array<string | null | undefined>) {
  const seen = new Set<string>()
  const normalizedKeys: string[] = []

  for (const ownerKey of ownerKeys ?? []) {
    const normalized = normalizeOwnerKey(ownerKey)
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    normalizedKeys.push(normalized)
  }

  return normalizedKeys
}

interface StoredHistoryEntry {
  sessionId?: string
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
  const persistentStoreRef = getPersistentStoreSafe()
  const localEntries = parseStoredEntries<T>(persistentStoreRef?.getItem(storageKey) ?? null)

  if (localEntries) {
    return localEntries
  }

  if (normalizeOwnerKey(ownerKey)) {
    return []
  }

  const transientStoreRef = getTransientStoreSafe()
  const legacyEntries = parseStoredEntries<T>(transientStoreRef?.getItem(HISTORY_STORAGE_KEY) ?? null)

  if (!legacyEntries) {
    return []
  }

  if (persistentStoreRef) {
    try {
      persistentStoreRef.setItem(HISTORY_STORAGE_KEY, JSON.stringify(legacyEntries))
      transientStoreRef?.removeItem(HISTORY_STORAGE_KEY)
    } catch {
      // Keep using the legacy transient copy when persistent-store writes fail.
    }
  }

  return legacyEntries
}

export function savePersistedReviewHistory<T>(entries: T[], ownerKey?: string | null) {
  const storageKey = buildScopedHistoryStorageKey(ownerKey)
  const serializedEntries = JSON.stringify(entries)
  const persistentStoreRef = getPersistentStoreSafe()

  if (persistentStoreRef) {
    try {
      persistentStoreRef.setItem(storageKey, serializedEntries)
      getTransientStoreSafe()?.removeItem(storageKey)
      if (storageKey !== HISTORY_STORAGE_KEY) {
        getTransientStoreSafe()?.removeItem(HISTORY_STORAGE_KEY)
      }
      return
    } catch {
      // Fall through to transient storage if the persistent store is unavailable.
    }
  }

  getTransientStoreSafe()?.setItem(storageKey, serializedEntries)
}

export function loadPersistedReviewHistoryFromOwners<T = unknown>(ownerKeys?: Array<string | null | undefined>): T[] {
  const mergedEntries: T[] = []
  const seenEntries = new Set<string>()

  for (const ownerKey of normalizeOwnerKeys(ownerKeys)) {
    const entries = loadPersistedReviewHistory<T>(ownerKey)
    for (const entry of entries) {
      const entryKey = JSON.stringify(entry)
      if (seenEntries.has(entryKey)) continue
      seenEntries.add(entryKey)
      mergedEntries.push(entry)
    }
  }

  return mergedEntries
}

export function deletePersistedReviewHistoryEntry(
  sessionId: string,
  ownerKeys?: Array<string | null | undefined>,
) {
  const normalizedOwnerKeys = normalizeOwnerKeys(ownerKeys)
  const ownersToUpdate: Array<string | null> = normalizedOwnerKeys.length > 0 ? normalizedOwnerKeys : [null]
  let deleted = false

  for (const ownerKey of ownersToUpdate) {
    const entries = loadPersistedReviewHistory<StoredHistoryEntry>(ownerKey)
    const filteredEntries = entries.filter((entry) => entry?.sessionId !== sessionId)

    if (filteredEntries.length === entries.length) {
      continue
    }

    savePersistedReviewHistory(filteredEntries, ownerKey)
    deleted = true
  }

  return deleted
}

