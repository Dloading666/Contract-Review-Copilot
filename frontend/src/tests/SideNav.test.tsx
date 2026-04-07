import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SideNav } from '../components/SideNav'

describe('SideNav', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('shows history dropdown when clicking 对话历史, closes when clicking 实时对话', () => {
    sessionStorage.setItem('reviewHistory', JSON.stringify([
      { sessionId: 'session-1', filename: '合同A.txt', date: '2026/04/07 21:00:00' },
    ]))

    render(<SideNav />)

    fireEvent.click(screen.getByRole('button', { name: /对话历史/ }))
    expect(screen.getByText('审查历史')).toBeTruthy()
    expect(screen.getByText('合同A.txt')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /实时对话/ }))
    expect(screen.queryByText('审查历史')).toBeNull()
  })

  it('calls onSelectHistorySession when a history item is clicked', () => {
    sessionStorage.setItem('reviewHistory', JSON.stringify([
      { sessionId: 'session-42', filename: '测试合同.docx', date: '2026/04/07' },
    ]))

    const onSelect = vi.fn()
    render(<SideNav onSelectHistorySession={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /对话历史/ }))
    fireEvent.click(screen.getByText('测试合同.docx'))
    expect(onSelect).toHaveBeenCalledWith('session-42')
  })

  it('shows settings content in the lower-left menu and triggers logout', () => {
    const onLogout = vi.fn()

    render(
      <SideNav
        user={{ email: 'demo@example.com', id: 'demo' }}
        onLogout={onLogout}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /设置/ }))
    expect(screen.getByText('当前账号')).toBeTruthy()
    expect(screen.getByText('demo@example.com')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /退出登录/ }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
