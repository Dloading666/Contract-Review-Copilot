import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from '../pages/RegisterPage'

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    text: async () => JSON.stringify(payload),
  }
}

describe('RegisterPage', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('sends anti-bot fields when requesting an email code', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ success: true }))
    const nowSpy = vi.spyOn(Date, 'now')
    nowSpy.mockReturnValueOnce(1000)
    nowSpy.mockReturnValue(3200)
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<RegisterPage onNavigateLogin={vi.fn()} />)
    const emailInput = container.querySelector('input[placeholder="name@example.com"]') as HTMLInputElement
    const sendCodeButton = container.querySelector('.auth-code-row__button') as HTMLButtonElement

    fireEvent.change(emailInput, { target: { value: 'demo@example.com' } })
    fireEvent.click(sendCodeButton)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>
    const options = calls[0]?.[1]
    const payload = JSON.parse(String(options?.body || '{}'))

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/send-code', expect.objectContaining({ method: 'POST' }))
    expect(payload.email).toBe('demo@example.com')
    expect(payload.website).toBe('')
    expect(payload.captcha_token).toBeNull()
    expect(payload.client_elapsed_ms).toBeGreaterThanOrEqual(2000)
  })

  it('submits anti-bot fields during registration', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ success: true }))
    const nowSpy = vi.spyOn(Date, 'now')
    nowSpy.mockReturnValueOnce(1000)
    nowSpy.mockReturnValue(5000)
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<RegisterPage onNavigateLogin={vi.fn()} />)
    const inputs = Array.from(container.querySelectorAll('input')) as HTMLInputElement[]
    const emailInput = inputs.find((input) => input.placeholder === 'name@example.com') as HTMLInputElement
    const codeInput = inputs.find((input) => input.placeholder.includes('6')) as HTMLInputElement
    const passwordInputs = inputs.filter((input) => input.type === 'password')
    const submitButton = container.querySelector('.auth-submit') as HTMLButtonElement

    fireEvent.change(emailInput, { target: { value: 'demo@example.com' } })
    fireEvent.change(codeInput, { target: { value: '123456' } })
    fireEvent.change(passwordInputs[0], { target: { value: 'Secret123' } })
    fireEvent.change(passwordInputs[1], { target: { value: 'Secret123' } })
    fireEvent.click(submitButton)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>
    const options = calls[0]?.[1]
    const payload = JSON.parse(String(options?.body || '{}'))

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/register', expect.objectContaining({ method: 'POST' }))
    expect(payload).toMatchObject({
      email: 'demo@example.com',
      code: '123456',
      password: 'Secret123',
      website: '',
      captcha_token: null,
    })
    expect(payload.client_elapsed_ms).toBeGreaterThanOrEqual(4000)

    await waitFor(() => expect(container.querySelector('.auth-success')).toBeTruthy())
  })
})

