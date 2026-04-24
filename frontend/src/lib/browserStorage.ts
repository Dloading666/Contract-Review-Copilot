type BrowserStorageKind = "local" | "session"

function getStorage(kind: BrowserStorageKind): Storage | null {
  if (typeof window === 'undefined') return null

  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function getLocalStorageSafe() {
  return getStorage('local')
}

export function getSessionStorageSafe() {
  return getStorage('session')
}

export function readSessionReportSnapshot() {
  return getSessionStorageSafe()?.getItem('lastReport') ?? null
}

export function writeSessionReportSnapshot(paragraphs: string[]) {
  try {
    getSessionStorageSafe()?.setItem('lastReport', paragraphs.join('\n\n'))
  } catch {
    // Ignore storage failures in private mode or restrictive environments.
  }
}

export function getPersistentStoreSafe() {
  return getStorage('local')
}

export function getTransientStoreSafe() {
  return getStorage('session')
}
