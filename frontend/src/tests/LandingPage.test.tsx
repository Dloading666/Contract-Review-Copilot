import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LandingPage } from '../pages/LandingPage'

describe('LandingPage', () => {
  afterEach(() => {
    cleanup()
    window.sessionStorage.clear()
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

  it('links the top navigation GitHub button to the repository', () => {
    render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)

    const topbar = screen.getByRole('banner')
    const githubLink = within(topbar).getByRole('link', { name: /GitHub/i })

    expect(githubLink.getAttribute('href')).toBe('https://github.com/Dloading666/Contract-Review-Copilot')
    expect(githubLink.getAttribute('target')).toBe('_blank')
  })

  it('links the claude legal skill source card to the upstream repository', () => {
    render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)

    const sourceLink = screen.getByRole('link', { name: 'claude-legal-skill' })

    expect(sourceLink.getAttribute('href')).toBe('https://github.com/evolsb/claude-legal-skill')
    expect(sourceLink.getAttribute('target')).toBe('_blank')
  })

  it('shows a welcome star prompt and remembers dismissal for the session', () => {
    const { unmount } = render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)

    expect(screen.getByRole('dialog', { name: '欢迎浏览和使用该产品！' })).not.toBeNull()
    const starLink = screen.getByRole('link', { name: '去 GitHub 点 Star' })
    expect(starLink.getAttribute('href')).toBe('https://github.com/Dloading666/Contract-Review-Copilot')

    fireEvent.click(screen.getByRole('button', { name: '先体验产品' }))
    expect(screen.queryByRole('dialog', { name: '欢迎浏览和使用该产品！' })).toBeNull()

    unmount()
    render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)
    expect(screen.queryByRole('dialog', { name: '欢迎浏览和使用该产品！' })).toBeNull()
  })

  it('removes the named testimonial attribution from the hero note', () => {
    render(<LandingPage onNavigateLogin={vi.fn()} onNavigateRegister={vi.fn()} />)

    expect(screen.queryByText('某科技公司法务负责人')).toBeNull()
  })

  it('makes the footer legal and contact links navigable', () => {
    const onNavigatePrivacy = vi.fn()
    const onNavigateTerms = vi.fn()

    render(
      <LandingPage
        onNavigateLogin={vi.fn()}
        onNavigateRegister={vi.fn()}
        onNavigatePrivacy={onNavigatePrivacy}
        onNavigateTerms={onNavigateTerms}
      />,
    )

    const privacyLink = screen.getByRole('link', { name: '隐私政策' })
    const termsLink = screen.getByRole('link', { name: '服务条款' })
    const contactLink = screen.getByRole('link', { name: '联系我们' })

    expect(privacyLink.getAttribute('href')).toBe('/privacy')
    expect(termsLink.getAttribute('href')).toBe('/terms')
    expect(contactLink.getAttribute('href')).toBe('https://github.com/Dloading666/Contract-Review-Copilot/issues')
    expect(contactLink.getAttribute('target')).toBe('_blank')

    fireEvent.click(privacyLink)
    fireEvent.click(termsLink)

    expect(onNavigatePrivacy).toHaveBeenCalledTimes(1)
    expect(onNavigateTerms).toHaveBeenCalledTimes(1)
  })
})
