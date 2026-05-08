import { useEffect, useRef } from 'react'
import { Github } from 'lucide-react'

import dogeArchitectImage from '../assets/landing/doge-architect.jpg'
import '../styles/landing.css'

interface LandingPageProps {
  onNavigateLogin: () => void
  onNavigateRegister: () => void
}

const featureCards = [
  {
    icon: 'bolt',
    toneClass: 'landing-feature-card__icon--green',
    title: '秒速风险扫描',
    description: '上传即分析，快速识别显失公平、违约责任模糊、押金陷阱等 50+ 类合同风险。',
  },
  {
    icon: 'find_in_page',
    toneClass: 'landing-feature-card__icon--amber',
    title: '逐条条款解析',
    description: '不仅指出问题，还会逐项解释条款含义，让你真正看懂每一份合同背后的法律风险。',
  },
  {
    icon: 'gavel',
    toneClass: 'landing-feature-card__icon--blue',
    title: '合规修改建议',
    description: '结合民法典与实务经验，直接给出可落地的修改建议，帮助你更稳妥地签约。',
  },
] as const

const steps = [
  {
    number: '01',
    title: '上传合同',
    description: '支持 PDF、Word、图片等多种格式',
    accentClass: 'landing-step__badge--green',
  },
  {
    number: '02',
    title: '智能分析',
    description: 'AI 引擎逐行审查，快速定位关键风险',
    accentClass: 'landing-step__badge--amber',
  },
  {
    number: '03',
    title: '获取建议',
    description: '生成完整报告，并给出可执行修改意见',
    accentClass: 'landing-step__badge--blue',
  },
] as const

const stats: Array<{ label: string; value: string; wide?: boolean }> = [
  { label: '数据来源', value: 'CUAD 数据集' },
  { label: '训练样本', value: '510 份真实法律合同' },
  { label: '风险覆盖', value: '41 类核心法律风险识别', wide: true },
] as const

const testimonials = [
  {
    quote: '“作为创业团队负责人，我最怕合同里的隐形风险。这个工具帮我在签字前把坑先看出来了。”',
    name: '李先生',
    title: '独立开发者',
    accentClass: 'landing-testimonial__avatar--green',
    variantClass: '',
  },
  {
    quote: '“第一次看到合同审查还能做得这么直观。结构清楚、速度快，重点风险一眼就能抓住。”',
    name: '张女士',
    title: '初创公司合伙人',
    accentClass: 'landing-testimonial__avatar--amber',
    variantClass: 'landing-testimonial--offset',
  },
] as const

const footerLinks = ['隐私政策', '服务条款', '联系我们'] as const
const GITHUB_REPOSITORY_URL = 'https://github.com/Dloading666/Contract-Review-Copilot'

export function LandingPage({ onNavigateLogin, onNavigateRegister }: LandingPageProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    document.body.classList.add('landing-page-active')

    return () => {
      document.body.classList.remove('landing-page-active')
    }
  }, [])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return

    const revealTargets = Array.from(root.querySelectorAll<HTMLElement>('[data-landing-reveal]'))
    if (revealTargets.length === 0) return

    const prefersReducedMotion = typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (prefersReducedMotion || typeof IntersectionObserver === 'undefined') {
      revealTargets.forEach((element) => element.classList.add('is-visible'))
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        })
      },
      {
        threshold: 0.18,
        rootMargin: '0px 0px -10% 0px',
      },
    )

    revealTargets.forEach((element) => observer.observe(element))

    return () => observer.disconnect()
  }, [])

  return (
    <div ref={rootRef} className="landing-page">
      <header className="landing-topbar">
        <div className="landing-topbar__brand">合同审查全能扫描</div>
        <div className="landing-topbar__actions">
          <a
            className="brutalist-button landing-button landing-button--github"
            href={GITHUB_REPOSITORY_URL}
            target="_blank"
            rel="noreferrer"
          >
            <Github size={18} strokeWidth={3} />
            GitHub
          </a>
          <button type="button" className="brutalist-button landing-button landing-button--ghost" onClick={onNavigateLogin}>
            登录
          </button>
          <button type="button" className="brutalist-button landing-button landing-button--primary" onClick={onNavigateRegister}>
            免费注册
          </button>
        </div>
      </header>

      <main className="landing-main">
        <section className="landing-hero">
          <div className="landing-hero__free" aria-hidden="true">FREE</div>

          <div className="landing-hero__content landing-reveal landing-reveal--0" data-landing-reveal>
            <div className="landing-hero__badge">100% 免费使用</div>
            <h1 className="landing-hero__title">
              AI 智能合同审查
              <span>免费使用 规避风险</span>
            </h1>
            <p className="landing-hero__description">
              像架构师一样拆解合同结构。上传一份合同，我们会帮你快速识别风险条款、给出修改建议，并用更清晰的方式展示法律依据。
            </p>
            <div className="landing-hero__actions">
              <button type="button" className="brutalist-button landing-button landing-button--hero" onClick={onNavigateRegister}>
                立即免费审查
              </button>
              <button type="button" className="brutalist-button landing-button landing-button--secondary" onClick={onNavigateLogin}>
                已有账号登录
              </button>
            </div>
            <div className="landing-hero__security">
              <span className="material-symbols-outlined">verified_user</span>
              <span>100% 隐私安全加密</span>
            </div>
          </div>

          <div className="landing-hero__visual landing-reveal landing-reveal--1" data-landing-reveal>
            <div className="landing-hero__visual-shell">
              <div className="landing-hero__frame brutalist-card">
                <img className="landing-hero__image" src={dogeArchitectImage} alt="AI 合同审查助手主视觉" />
              </div>
            </div>
            <div className="landing-hero__note-shell">
              <div className="landing-hero__note brutalist-card">
                <p>“审查速度太快了，而且居然是免费的！”</p>
                <span>某科技公司法务负责人</span>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-features">
          <div className="landing-features__grid">
            {featureCards.map((card, index) => (
              <article
                key={card.title}
                className={`landing-feature-card brutalist-card landing-reveal landing-reveal--${(index + 1) as 1 | 2 | 3}`}
                data-landing-reveal
              >
                <div className={`landing-feature-card__icon ${card.toneClass}`}>
                  <span className="material-symbols-outlined">{card.icon}</span>
                </div>
                <h2>{card.title}</h2>
                <p>{card.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-steps landing-reveal landing-reveal--1" data-landing-reveal>
          <h2 className="landing-section-title">三个步骤，掌控契约</h2>
          <div className="landing-steps__grid">
            {steps.map((step, index) => (
              <div key={step.number} className="landing-step">
                <div className={`landing-step__badge brutalist-card ${step.accentClass}`}>{step.number}</div>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
                {index < steps.length - 1 ? <div className="landing-step__line" aria-hidden="true" /> : null}
              </div>
            ))}
          </div>
        </section>

        <section className="landing-tech landing-reveal landing-reveal--2" data-landing-reveal>
          <div className="landing-tech__panel brutalist-card">
            <div className="landing-tech__label">Technology Source</div>
            <div className="landing-tech__layout">
              <div className="landing-tech__brand">
                <div className="landing-tech__brand-mark brutalist-card" aria-hidden="true">
                  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
                  </svg>
                </div>
                <div className="landing-tech__brand-copy">
                  <span>claude-legal-skill</span>
                  <small>(Community Version)</small>
                </div>
              </div>

              <div className="landing-tech__content">
                <h2>由业界领先的法律 AI 框架驱动</h2>
                <p>
                  我们把社区里成熟的法律审查方法论重新打磨成可直接使用的产品体验，让每一位普通用户也能像专业法务一样看懂合同。
                </p>
                <div className="landing-tech__stats">
                  {stats.map((stat) => (
                    <div
                      key={stat.label}
                      className={`landing-tech__stat ${stat.wide === true ? 'landing-tech__stat--wide' : ''}`}
                    >
                      <span>{stat.label}</span>
                      <strong>{stat.value}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-disclaimer landing-reveal landing-reveal--1" data-landing-reveal>
          <div className="landing-disclaimer__panel brutalist-card">
            <div className="landing-disclaimer__icon-shell" aria-hidden="true">
              <div className="landing-disclaimer__icon-box">
                <span className="material-symbols-outlined">warning</span>
              </div>
            </div>
            <p className="landing-disclaimer__text">
              <strong>免责声明：</strong>
              本网页提供的所有信息及审查结果仅供参考，不构成任何形式的法律建议或专业意见。用户在使用本工具时应自行承担相应风险，建议在处理重要法律事务时咨询专业律师。
            </p>
          </div>
        </section>

        <section className="landing-testimonials">
          <div className="landing-testimonials__grid">
            {testimonials.map((item, index) => (
              <article
                key={item.name}
                className={`landing-testimonial ${item.variantClass} landing-reveal landing-reveal--${(index + 1) as 1 | 2}`}
                data-landing-reveal
              >
                <div className="landing-testimonial__bubble brutalist-card">
                  <p>{item.quote}</p>
                  <div className="landing-testimonial__tail" aria-hidden="true" />
                </div>
                <div className="landing-testimonial__meta">
                  <div className={`landing-testimonial__avatar ${item.accentClass}`} aria-hidden="true" />
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.title}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-cta landing-reveal landing-reveal--1" data-landing-reveal>
          <div className="landing-cta__panel brutalist-card">
            <h2>
              别让法律漏洞
              <br />
              毁掉你的生意
            </h2>
            <p>从上传合同到生成修改建议，只需要几分钟，就能先把明显风险看清楚。</p>
            <div className="landing-cta__actions">
              <button type="button" className="brutalist-button landing-button landing-button--dark" onClick={onNavigateRegister}>
                立即免费试用
              </button>
              <button type="button" className="brutalist-button landing-button landing-button--light" onClick={onNavigateLogin}>
                登录继续使用
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-footer__copyright">© 2026 ANALOG ARCHITECT. 保留所有权利。</div>
        <div className="landing-footer__links">
          {footerLinks.map((label) => (
            <button key={label} type="button" className="landing-footer__link">
              {label}
            </button>
          ))}
        </div>
        <div className="landing-footer__badge">为所有法律专业人士和开发者免费提供</div>
      </footer>
    </div>
  )
}
