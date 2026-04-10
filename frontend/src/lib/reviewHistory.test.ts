import { beforeEach, describe, expect, it } from 'vitest'
import { loadPersistedReviewHistory, loadPersistedReviewHistoryFromOwners, savePersistedReviewHistory } from './reviewHistory'

describe('reviewHistory storage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('persists history entries in localStorage', () => {
    savePersistedReviewHistory([
      { sessionId: 'session-1', filename: 'contract-a.docx', date: '2026/04/08 10:00:00' },
    ], 'demo@example.com')

    expect(loadPersistedReviewHistory<{ sessionId: string }>('demo@example.com'))
      .toEqual([{ sessionId: 'session-1', filename: 'contract-a.docx', date: '2026/04/08 10:00:00' }])
    expect(localStorage.getItem('reviewHistory:demo@example.com')).toContain('session-1')
    expect(localStorage.getItem('reviewHistory')).toBeNull()
    expect(sessionStorage.getItem('reviewHistory:demo@example.com')).toBeNull()
  })

  it('migrates legacy history entries from sessionStorage', () => {
    sessionStorage.setItem('reviewHistory', JSON.stringify([
      { sessionId: 'legacy-session', filename: 'legacy.pdf', date: '2026/04/07 09:00:00' },
    ]))

    expect(loadPersistedReviewHistory<{ sessionId: string }>())
      .toEqual([{ sessionId: 'legacy-session', filename: 'legacy.pdf', date: '2026/04/07 09:00:00' }])
    expect(localStorage.getItem('reviewHistory')).toContain('legacy-session')
    expect(sessionStorage.getItem('reviewHistory')).toBeNull()
  })

  it('keeps histories isolated between different users', () => {
    savePersistedReviewHistory([
      { sessionId: 'session-a', filename: 'alice.docx', date: '2026/04/08 10:00:00' },
    ], 'alice@example.com')
    savePersistedReviewHistory([
      { sessionId: 'session-b', filename: 'bob.docx', date: '2026/04/08 11:00:00' },
    ], 'bob@example.com')

    expect(loadPersistedReviewHistory<{ sessionId: string }>('alice@example.com'))
      .toEqual([{ sessionId: 'session-a', filename: 'alice.docx', date: '2026/04/08 10:00:00' }])
    expect(loadPersistedReviewHistory<{ sessionId: string }>('bob@example.com'))
      .toEqual([{ sessionId: 'session-b', filename: 'bob.docx', date: '2026/04/08 11:00:00' }])
  })

  it('does not fall back to legacy global history for a signed-in user', () => {
    localStorage.setItem('reviewHistory', JSON.stringify([
      { sessionId: 'legacy-global', filename: 'legacy.docx', date: '2026/04/08 10:00:00' },
    ]))

    expect(loadPersistedReviewHistory<{ sessionId: string }>('scoped@example.com')).toEqual([])
  })

  it('loads history from multiple owner aliases', () => {
    savePersistedReviewHistory([
      { sessionId: 'session-email', filename: 'email.docx', date: '2026/04/08 10:00:00' },
    ], 'legacy@example.com')
    savePersistedReviewHistory([
      { sessionId: 'session-phone', filename: 'phone.docx', date: '2026/04/08 11:00:00' },
    ], '13800138000')

    expect(loadPersistedReviewHistoryFromOwners<{ sessionId: string }>([
      'user-123',
      '13800138000',
      'legacy@example.com',
    ])).toEqual([
      { sessionId: 'session-phone', filename: 'phone.docx', date: '2026/04/08 11:00:00' },
      { sessionId: 'session-email', filename: 'email.docx', date: '2026/04/08 10:00:00' },
    ])
  })
})
