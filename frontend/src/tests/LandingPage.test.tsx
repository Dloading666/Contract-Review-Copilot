import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LandingPage } from '../pages/LandingPage'

describe('LandingPage', () => {
  afterEach(() => {
    cleanup()
    document.body.classList.remove('landing-page-active')
  })

  it('renders the marketing hero content', () => {
    render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)

    expect(screen.getByText('合同审查全能扫描')).not.toBeNull()
    expect(screen.getByRole('heading', { name: /AI 智能合同审查/i })).not.toBeNull()
    expect(screen.getByText('由业界领先的法律 AI 框架驱动')).not.toBeNull()
    expect(screen.getByText(/本网页提供的所有信息及审查结果仅供参考/)).not.toBeNull()
  })

  it('keeps login and register actions wired to the existing auth flow', () => {
    const onNavigateLogin = vi.fn()
    const onNavigateRegister = vi.fn()

    render(<LandingPage onNavigateLogin={onNavigateLogin} onNavigateRegister={onNavigateRegister} />)

    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    fireEvent.click(screen.getByRole('button', { name: '免费注册' }))
    fireEvent.click(screen.getByRole('button', { name: '立即免费审查' }))

    expect(onNavigateLogin).toHaveBeenCalledTimes(1)
    expect(onNavigateRegister).toHaveBeenCalledTimes(2)
  })
})
