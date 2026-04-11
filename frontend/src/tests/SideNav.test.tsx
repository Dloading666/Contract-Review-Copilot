import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SideNav } from '../components/SideNav'
import type { User } from '../contexts/AuthContext'

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: 'demo',
    email: 'demo@example.com',
    emailVerified: true,
    accountStatus: 'active',
    createdAt: '2026-04-09T00:00:00Z',
    ...overrides,
  }
}

describe('SideNav', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows history dropdown and closes it when switching back to chat', () => {
    localStorage.setItem('reviewHistory:demo', JSON.stringify([
      { sessionId: 'session-1', filename: '合同A.txt', date: '2026/04/07 21:00:00' },
    ]))

    const view = render(<SideNav user={buildUser()} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))
    expect(view.getAllByText('审查历史').length).toBeGreaterThan(1)
    expect(view.getByText('合同A.txt')).toBeTruthy()

    fireEvent.click(view.getByRole('button', { name: /实时对话/ }))
    expect(view.queryByText('合同A.txt')).toBeNull()
  })

  it('shows a readable empty state when there is no review history', () => {
    const view = render(<SideNav user={buildUser()} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))

    expect(view.getByText('暂无历史记录')).toBeTruthy()
  })

  it('calls onSelectHistorySession when a history item is clicked', () => {
    localStorage.setItem('reviewHistory:demo', JSON.stringify([
      { sessionId: 'session-42', filename: '测试合同.docx', date: '2026/04/07' },
    ]))

    const onSelect = vi.fn()
    const view = render(<SideNav user={buildUser()} onSelectHistorySession={onSelect} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))
    fireEvent.click(view.getByText('测试合同.docx'))
    expect(onSelect).toHaveBeenCalledWith('session-42')
  })

  it('deletes a review history entry after confirmation', () => {
    localStorage.setItem('reviewHistory:demo', JSON.stringify([
      { sessionId: 'session-delete', filename: '待删除合同.docx', date: '2026/04/07' },
      { sessionId: 'session-keep', filename: '保留合同.docx', date: '2026/04/08' },
    ]))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onDelete = vi.fn()

    const view = render(<SideNav user={buildUser()} onDeleteHistorySession={onDelete} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))
    fireEvent.click(view.getByRole('button', { name: /删除审查历史 待删除合同\.docx/ }))

    expect(confirmSpy).toHaveBeenCalledWith('确定删除「待删除合同.docx」这条审查历史吗？')
    expect(onDelete).toHaveBeenCalledWith('session-delete')
    expect(view.queryByText('待删除合同.docx')).toBeNull()
    expect(view.getByText('保留合同.docx')).toBeTruthy()
    expect(localStorage.getItem('reviewHistory:demo')).not.toContain('session-delete')
  })

  it('keeps a review history entry when deletion is canceled', () => {
    localStorage.setItem('reviewHistory:demo', JSON.stringify([
      { sessionId: 'session-keep', filename: '不删除合同.docx', date: '2026/04/07' },
    ]))
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const onDelete = vi.fn()

    const view = render(<SideNav user={buildUser()} onDeleteHistorySession={onDelete} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))
    fireEvent.click(view.getByRole('button', { name: /删除审查历史 不删除合同\.docx/ }))

    expect(view.getByText('不删除合同.docx')).toBeTruthy()
    expect(onDelete).not.toHaveBeenCalled()
    expect(localStorage.getItem('reviewHistory:demo')).toContain('session-keep')
  })

  it('only shows history entries belonging to the signed-in user', () => {
    localStorage.setItem('reviewHistory:alice', JSON.stringify([
      { sessionId: 'alice-session', filename: 'alice.docx', date: '2026/04/07 21:00:00' },
    ]))
    localStorage.setItem('reviewHistory:bob', JSON.stringify([
      { sessionId: 'bob-session', filename: 'bob.docx', date: '2026/04/07 22:00:00' },
    ]))

    const view = render(<SideNav user={buildUser({ id: 'bob', email: 'bob@example.com' })} />)

    fireEvent.click(view.getByRole('button', { name: /审查历史/ }))

    expect(view.getByText('bob.docx')).toBeTruthy()
    expect(view.queryByText('alice.docx')).toBeNull()
  })

  it('shows user email and triggers logout', () => {
    const onLogout = vi.fn()

    const view = render(
      <SideNav
        user={buildUser()}
        onLogout={onLogout}
      />,
    )

    expect(view.getByText('demo@example.com')).toBeTruthy()

    fireEvent.click(view.getByRole('button', { name: /退出登录/ }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
