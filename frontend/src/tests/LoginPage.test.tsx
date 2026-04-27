import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from '../pages/LoginPage'

describe('LoginPage', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  afterEach(() => {
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
})
