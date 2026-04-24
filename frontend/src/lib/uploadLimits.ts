export const MAX_CONTRACT_UPLOAD_FILE_BYTES = 20 * 1024 * 1024
export const MAX_CONTRACT_IMAGE_BATCH = 12

export function formatUploadBytes(bytes: number) {
  if (bytes >= 1024 * 1024) {
    const megabytes = bytes / (1024 * 1024)
    return Number.isInteger(megabytes) ? `${megabytes} MB` : `${megabytes.toFixed(1)} MB`
  }

  if (bytes >= 1024) {
    const kilobytes = bytes / 1024
    return Number.isInteger(kilobytes) ? `${kilobytes} KB` : `${kilobytes.toFixed(1)} KB`
  }

  return `${bytes} B`
}
