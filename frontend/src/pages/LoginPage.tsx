import { useState, useCallback } from 'react'
import './LoginPage.css'

interface LoginPageProps {
  onLogin: (token: string, user: { email: string; id: string }) => void
}

type Step = 'email' | 'code'

export function LoginPage({ onLogin }: LoginPageProps) {
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [countdown, setCountdown] = useState(0)

  const sendCode = useCallback(async () => {
    if (!email.trim()) {
      setError('请输入邮箱地址')
      return
    }
    if (!/^[\w\.-]+@[\w\.-]+\.\w+$/.test(email.trim())) {
      setError('请输入有效的邮箱格式')
      return
    }

    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/auth/send-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || '发送失败，请稍后重试')
        return
      }

      // Dev mode: show code if returned
      if (data.dev_code) {
        setCode(data.dev_code)
        setError('')
      }

      setStep('code')
      setCountdown(60)

      const timer = setInterval(() => {
        setCountdown(c => {
          if (c <= 1) {
            clearInterval(timer)
            return 0
          }
          return c - 1
        })
      }, 1000)

    } catch {
      setError('网络错误，请检查连接后重试')
    } finally {
      setLoading(false)
    }
  }, [email])

  const verifyCode = useCallback(async () => {
    if (code.length !== 6) {
      setError('请输入6位验证码')
      return
    }

    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), code: code.trim() }),
      })
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || '验证码错误或已过期')
        return
      }

      // Store token
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('auth_user', JSON.stringify(data.user))

      onLogin(data.token, data.user)

    } catch {
      setError('网络错误，请检查连接后重试')
    } finally {
      setLoading(false)
    }
  }, [email, code, onLogin])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (step === 'email') {
      sendCode()
    } else {
      verifyCode()
    }
  }

  const handleBack = () => {
    setStep('email')
    setCode('')
    setError('')
  }

  return (
    <div className="login-page">
      {/* Left brand panel */}
      <div className="login-page__brand">
        <div className="login-page__brand-bg">
          <div className="login-page__brand-blur login-page__brand-blur--1" />
          <div className="login-page__brand-blur login-page__brand-blur--2" />
        </div>
        <div className="login-page__brand-content">
          <div className="login-page__brand-logo">
            <span className="material-symbols-outlined login-page__logo-icon">verified_user</span>
            <span className="login-page__logo-text">合规智审 Copilot</span>
          </div>
          <div className="login-page__brand-headline">
            <h1>法律科技新范式<br />智能驱动契约信任</h1>
            <p>通过先进的 AI 语言模型，为您提供极速、精准的合同合规性审查与风险预警。</p>
          </div>
          <div className="login-page__brand-features">
            <div className="login-page__feature">
              <div className="login-page__feature-icon">
                <span className="material-symbols-outlined">verified_user</span>
              </div>
              <div>
                <p className="login-page__feature-title">安全可靠</p>
                <p className="login-page__feature-desc">金融级加密保护您的文档隐私</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="login-page__form-panel">
        <div className="login-page__form-container">
          <div className="login-page__form-header">
            <h2>欢迎登录</h2>
            <p>请使用您的专业账号访问平台</p>
          </div>

          <form className="login-page__form" onSubmit={handleSubmit}>
            {/* Email field — always shown */}
            <div className="login-page__field">
              <label className="login-page__label" htmlFor="email">邮箱地址</label>
              <div className="login-page__input-wrap">
                <span className="material-symbols-outlined login-page__input-icon">mail</span>
                <input
                  id="email"
                  type="email"
                  className="login-page__input"
                  placeholder="name@company.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  disabled={step === 'code'}
                  autoComplete="email"
                />
              </div>
            </div>

            {/* Verification code field */}
            {step === 'code' && (
              <div className="login-page__field">
                <label className="login-page__label" htmlFor="code">邮箱验证码</label>
                <div className="login-page__code-row">
                  <div className="login-page__input-wrap login-page__input-wrap--grow">
                    <span className="material-symbols-outlined login-page__input-icon">shield_person</span>
                    <input
                      id="code"
                      type="text"
                      className="login-page__input"
                      placeholder="6位验证码"
                      value={code}
                      onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      maxLength={6}
                      autoComplete="one-time-code"
                      autoFocus
                    />
                  </div>
                  <button
                    type="button"
                    className="login-page__send-btn"
                    onClick={sendCode}
                    disabled={loading || countdown > 0}
                  >
                    {countdown > 0 ? `${countdown}s` : '重新发送'}
                  </button>
                </div>

                {/* Dev mode: show code */}
                {code && (
                  <div className="login-page__dev-hint">
                    开发模式验证码：{code}
                  </div>
                )}
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="login-page__error">{error}</div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              className="login-page__submit"
              disabled={loading}
            >
              {loading ? (
                <span className="login-page__spinner" />
              ) : (
                <>
                  <span>{step === 'email' ? '发送验证码' : '登录'}</span>
                  <span className="material-symbols-outlined login-page__submit-icon">arrow_forward</span>
                </>
              )}
            </button>
          </form>

          {/* Back button when in code step */}
          {step === 'code' && (
            <button className="login-page__back" onClick={handleBack} type="button">
              <span className="material-symbols-outlined">arrow_back</span>
              返回修改邮箱
            </button>
          )}

          <p className="login-page__footer-text">
            还没有账号？
            <a className="login-page__link" href="#">立即申请试用</a>
          </p>
        </div>
      </div>
    </div>
  )
}
