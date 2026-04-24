import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ForgotPasswordPage } from '../pages/ForgotPasswordPage'
import { PASSWORD_POLICY_MESSAGE } from '../lib/passwordPolicy'

function createJSONResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('requests a reset code and shows the generic success state', async () => {
    const fetchMock = vi.fn(async () => createJSONResponse({
      success: true,
      message: '如果该邮箱已注册，我们已发送验证码，请查收邮箱',
      dev_code: '654321',
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ForgotPasswordPage onNavigateLogin={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('邮箱地址'), { target: { value: 'demo@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/password/send-reset-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'demo@example.com' }),
      })
    })

    expect(await screen.findByText('如果该邮箱已注册，我们已发送验证码，请查收邮箱')).not.toBeNull()
    expect(await screen.findByText('开发模式验证码：654321')).not.toBeNull()
  })

  it('blocks reset when the password is too weak', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<ForgotPasswordPage onNavigateLogin={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('邮箱地址'), { target: { value: 'demo@example.com' } })
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'weakpass' } })
    fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'weakpass' } })
    fireEvent.click(screen.getByRole('button', { name: '重置密码' }))

    expect((await screen.findAllByText(PASSWORD_POLICY_MESSAGE)).length).toBeGreaterThan(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits the reset request and navigates back to login on success', async () => {
    const onNavigateLogin = vi.fn()
    const fetchMock = vi.fn(async () => createJSONResponse({
      success: true,
      message: '密码重置成功，请返回登录',
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ForgotPasswordPage onNavigateLogin={onNavigateLogin} />)

    fireEvent.change(screen.getByLabelText('邮箱地址'), { target: { value: 'demo@example.com' } })
    fireEvent.change(screen.getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'NewSecret123' } })
    fireEvent.change(screen.getByLabelText('确认新密码'), { target: { value: 'NewSecret123' } })
    fireEvent.click(screen.getByRole('button', { name: '重置密码' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/password/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'demo@example.com',
          code: '123456',
          new_password: 'NewSecret123',
        }),
      })
    })

    expect(await screen.findByText('密码重置成功，请返回登录')).not.toBeNull()
    await new Promise((resolve) => setTimeout(resolve, 1600))
    expect(onNavigateLogin).toHaveBeenCalledTimes(1)
  })
})
