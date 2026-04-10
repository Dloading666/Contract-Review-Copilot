import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SettingsPage } from '../pages/SettingsPage'
import type { User } from '../contexts/AuthContext'

function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'demo@example.com',
    emailVerified: true,
    accountStatus: 'active',
    createdAt: '2026-04-10T00:00:00Z',
    ...overrides,
  }
}

describe('SettingsPage', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders account info and security center', () => {
    const { getAllByText, getByText } = render(
      <SettingsPage
        user={buildUser()}
        token="token-a"
        onUserUpdate={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    expect(getByText('账户中心')).not.toBeNull()
    expect(getByText('身份信息')).not.toBeNull()
    expect(getByText('安全中心')).not.toBeNull()
    expect(getAllByText('demo@example.com').length).toBeGreaterThan(0)
  })

  it('sends a password reset code and shows the dev code when returned', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ success: true, dev_code: '123456' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { getByRole, findByText } = render(
      <SettingsPage
        user={buildUser()}
        token="token-a"
        onUserUpdate={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    fireEvent.click(getByRole('button', { name: /发送验证码/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/security/send-password-code', {
        method: 'POST',
        headers: { Authorization: 'Bearer token-a' },
      })
    })

    expect(await findByText('开发环境验证码：123456')).not.toBeNull()
  })

  it('blocks submit when passwords do not match', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { getByLabelText, getByRole, findByText } = render(
      <SettingsPage
        user={buildUser()}
        token="token-a"
        onUserUpdate={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    fireEvent.change(getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(getByLabelText('新密码'), { target: { value: 'newSecret123' } })
    fireEvent.change(getByLabelText('确认新密码'), { target: { value: 'anotherSecret' } })
    fireEvent.click(getByRole('button', { name: /确认修改密码/i }))

    expect(await findByText('两次输入的新密码不一致。')).not.toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits a password reset request and clears the form on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, dev_code: '123456' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, message: '密码修改成功' }),
      })
    const onUserUpdate = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { getByLabelText, getByRole, findByText } = render(
      <SettingsPage
        user={buildUser()}
        token="token-a"
        onUserUpdate={onUserUpdate}
        onBack={vi.fn()}
      />,
    )

    fireEvent.change(getByLabelText('邮箱验证码'), { target: { value: '123456' } })
    fireEvent.change(getByLabelText('新密码'), { target: { value: 'newSecret123' } })
    fireEvent.change(getByLabelText('确认新密码'), { target: { value: 'newSecret123' } })
    fireEvent.click(getByRole('button', { name: /确认修改密码/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/auth/security/reset-password', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer token-a',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code: '123456',
          new_password: 'newSecret123',
        }),
      })
    })

    expect(await findByText('密码修改成功。')).not.toBeNull()
    expect((getByLabelText('邮箱验证码') as HTMLInputElement).value).toBe('')
    expect((getByLabelText('新密码') as HTMLInputElement).value).toBe('')
    expect((getByLabelText('确认新密码') as HTMLInputElement).value).toBe('')
    expect(onUserUpdate).toHaveBeenCalledWith(buildUser())
  })
})
