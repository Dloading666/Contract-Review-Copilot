const DISCLAIMER_ACCEPTANCE_STORAGE_KEY_PREFIX = 'contractReviewDisclaimerAccepted:v2:'
const DISCLAIMER_ACCEPTANCE_VALUE = 'accepted'

function normalizeOwnerKey(ownerKey?: string | null) {
  return ownerKey?.trim().toLowerCase() || ''
}

export function getDisclaimerAcceptanceStorageKey(ownerKey?: string | null) {
  const normalizedOwnerKey = normalizeOwnerKey(ownerKey)
  return normalizedOwnerKey
    ? `${DISCLAIMER_ACCEPTANCE_STORAGE_KEY_PREFIX}${normalizedOwnerKey}`
    : DISCLAIMER_ACCEPTANCE_STORAGE_KEY_PREFIX
}

export function loadDisclaimerAcceptance(ownerKey?: string | null) {
  const normalizedOwnerKey = normalizeOwnerKey(ownerKey)
  if (!normalizedOwnerKey) {
    return false
  }

  try {
    return localStorage.getItem(getDisclaimerAcceptanceStorageKey(normalizedOwnerKey)) === DISCLAIMER_ACCEPTANCE_VALUE
  } catch {
    return false
  }
}

export function persistDisclaimerAcceptance(ownerKey?: string | null) {
  const normalizedOwnerKey = normalizeOwnerKey(ownerKey)
  if (!normalizedOwnerKey) {
    return
  }

  try {
    localStorage.setItem(getDisclaimerAcceptanceStorageKey(normalizedOwnerKey), DISCLAIMER_ACCEPTANCE_VALUE)
  } catch {
    // Ignore storage failures so the user can still continue in this session.
  }
}
