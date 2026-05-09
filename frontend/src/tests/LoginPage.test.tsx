import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from '../pages/LoginPage'

describe('LoginPage', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  it('keeps register and forgot-password navigation actions wired', () => {
    const onNavigateRegister = vi.fn()
    const onNavigateForgotPassword = vi.fn()

    render(
      <LoginPage
        onLogin={vi.fn()}
        onNavigateRegister={onNavigateRegister}
        onNavigateForgotPassword={onNavigateForgotPassword}
        onNavigateLanding={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '忘记密码？' }))
    fireEvent.click(screen.getByRole('button', { name: '邮箱注册' }))

    expect(onNavigateForgotPassword).toHaveBeenCalledTimes(1)
    expect(onNavigateRegister).toHaveBeenCalledTimes(1)
  })

  it('renders GitHub and Google OAuth login entries', () => {
    render(
      <LoginPage
        onLogin={vi.fn()}
        onNavigateRegister={vi.fn()}
        onNavigateForgotPassword={vi.fn()}
        onNavigateLanding={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'GitHub 登录' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Google 邮箱登录' })).toBeTruthy()
  })

  it('shows the backend login error instead of an expired-session message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ error: '邮箱或密码错误' }),
      headers: new Headers({ 'content-type': 'application/json' }),
    }))

    render(
      <LoginPage
        onLogin={vi.fn()}
        onNavigateRegister={vi.fn()}
        onNavigateForgotPassword={vi.fn()}
        onNavigateLanding={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('name@example.com'), {
      target: { value: 'user@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), {
      target: { value: 'wrong-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: '邮箱登录' }))

    await waitFor(() => {
      expect(screen.getByText('邮箱或密码错误')).toBeTruthy()
    })
    expect(screen.queryByText('登录已过期，请重新登录')).toBeNull()
  })
})
