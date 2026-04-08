import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SideNav } from '../components/SideNav'

describe('SideNav', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('shows history dropdown when clicking 审查历史, closes when clicking 实时对话', () => {
    localStorage.setItem('reviewHistory:demo@example.com', JSON.stringify([
      { sessionId: 'session-1', filename: '合同A.txt', date: '2026/04/07 21:00:00' },
    ]))

    render(<SideNav user={{ email: 'demo@example.com', id: 'demo' }} />)

    fireEvent.click(screen.getByRole('button', { name: /审查历史/ }))
    expect(screen.getAllByText('审查历史').length).toBeGreaterThan(1)
    expect(screen.getByText('合同A.txt')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /实时对话/ }))
    expect(screen.queryByText('合同A.txt')).toBeNull()
  })

  it('shows a readable empty state when there is no review history', () => {
    render(<SideNav user={{ email: 'demo@example.com', id: 'demo' }} />)

    fireEvent.click(screen.getByRole('button', { name: /审查历史/ }))

    expect(screen.getByText('暂无历史记录')).toBeTruthy()
  })

  it('calls onSelectHistorySession when a history item is clicked', () => {
    localStorage.setItem('reviewHistory:demo@example.com', JSON.stringify([
      { sessionId: 'session-42', filename: '测试合同.docx', date: '2026/04/07' },
    ]))

    const onSelect = vi.fn()
    render(<SideNav user={{ email: 'demo@example.com', id: 'demo' }} onSelectHistorySession={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /审查历史/ }))
    fireEvent.click(screen.getByText('测试合同.docx'))
    expect(onSelect).toHaveBeenCalledWith('session-42')
  })

  it('only shows history entries belonging to the signed-in user', () => {
    localStorage.setItem('reviewHistory:alice@example.com', JSON.stringify([
      { sessionId: 'alice-session', filename: 'alice.docx', date: '2026/04/07 21:00:00' },
    ]))
    localStorage.setItem('reviewHistory:bob@example.com', JSON.stringify([
      { sessionId: 'bob-session', filename: 'bob.docx', date: '2026/04/07 22:00:00' },
    ]))

    render(<SideNav user={{ email: 'bob@example.com', id: 'bob' }} />)

    fireEvent.click(screen.getByRole('button', { name: /审查历史/ }))

    expect(screen.getByText('bob.docx')).toBeTruthy()
    expect(screen.queryByText('alice.docx')).toBeNull()
  })

  it('shows user email and triggers logout', () => {
    const onLogout = vi.fn()

    render(
      <SideNav
        user={{ email: 'demo@example.com', id: 'demo' }}
        onLogout={onLogout}
      />,
    )

    expect(screen.getByText('demo@example.com')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /退出登录/ }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
