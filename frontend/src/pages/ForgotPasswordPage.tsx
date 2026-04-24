import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, KeyRound, Lock, Mail, ShieldCheck } from 'lucide-react'
import { safeFetchJSON } from '../lib/apiClient'
import { apiPath } from '../lib/apiPaths'
import { getPasswordValidationError, PASSWORD_POLICY_MESSAGE } from '../lib/passwordPolicy'

interface ForgotPasswordPageProps {
  onNavigateLogin: () => void
}

interface SendResetCodeResponse {
  success?: boolean
  message?: string
  dev_code?: string
  error?: string
}

interface ResetPasswordResponse {
  success?: boolean
  message?: string
  error?: string
}

const EMAIL_PATTERN = /^[\w.-]+@[\w.-]+\.\w+$/

export function ForgotPasswordPage({ onNavigateLogin }: ForgotPasswordPageProps) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [sendingCode, setSendingCode] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [devCode, setDevCode] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const redirectTimerRef = useRef<number | null>(null)

  const passwordValidationError = password ? getPasswordValidationError(password) : null
  const passwordMismatch = confirmPassword.length > 0 && password !== confirmPassword

  useEffect(() => {
    if (countdown <= 0) return undefined
    const timer = window.setInterval(() => {
      setCountdown((value) => (value > 0 ? value - 1 : 0))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [countdown])

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) {
        window.clearTimeout(redirectTimerRef.current)
      }
    }
  }, [])

  const handleSendCode = async () => {
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail) {
      setError('请输入邮箱地址')
      return
    }
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError('请输入有效的邮箱地址')
      return
    }

    setSendingCode(true)
    setError('')
    setSuccess('')
    setDevCode('')
    try {
      const payload = await safeFetchJSON<SendResetCodeResponse>(apiPath('/auth/password/send-reset-code'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail }),
      })
      setSuccess(payload.message || '如果该邮箱已注册，我们已发送验证码，请查收邮箱。')
      setDevCode(payload.dev_code ?? '')
      setCountdown(60)
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送验证码失败，请稍后重试')
    } finally {
      setSendingCode(false)
    }
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail || !code.trim() || !password.trim() || !confirmPassword.trim()) {
      setError('请填写完整信息')
      return
    }
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setError('请输入有效的邮箱地址')
      return
    }
    if (passwordValidationError) {
      setError(passwordValidationError)
      return
    }
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致，请重新确认')
      return
    }

    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const payload = await safeFetchJSON<ResetPasswordResponse>(apiPath('/auth/password/reset'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: normalizedEmail,
          code: code.trim(),
          new_password: password,
        }),
      })
      setSuccess(payload.message || '密码重置成功！即将返回登录页...')
      redirectTimerRef.current = window.setTimeout(() => onNavigateLogin(), 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : '密码重置失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      <motion.div className="auth-card auth-card--narrow" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <div className="auth-card__form-pane auth-card__form-pane--full">
          <button type="button" className="auth-back-button" onClick={onNavigateLogin}>
            <ArrowLeft size={16} />
            返回登录
          </button>

          <div className="auth-register-copy">
            <h1>找回密码</h1>
            <p>通过注册邮箱接收验证码，验证成功后即可重新设置登录密码。</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <label className="auth-field">
              <span className="auth-field__label">邮箱地址</span>
              <div className="auth-field__control">
                <span className="auth-field__icon"><Mail size={16} /></span>
                <input
                  className="pixel-input pixel-input--literal auth-field__input"
                  placeholder="name@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                />
              </div>
            </label>

            <div className="auth-code-row">
              <label className="auth-field">
                <span className="auth-field__label">邮箱验证码</span>
                <div className="auth-field__control">
                  <span className="auth-field__icon"><ShieldCheck size={16} /></span>
                  <input
                    className="pixel-input pixel-input--literal auth-field__input"
                    placeholder="请输入 6 位验证码"
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                    autoComplete="one-time-code"
                  />
                </div>
              </label>
              <button
                type="button"
                className="pixel-button auth-code-row__button"
                onClick={handleSendCode}
                disabled={sendingCode || countdown > 0}
              >
                {countdown > 0 ? `${countdown}s` : sendingCode ? '发送中...' : '获取验证码'}
              </button>
            </div>

            {devCode && <div className="auth-dev-code">开发模式验证码：{devCode}</div>}

            <label className="auth-field">
              <span className="auth-field__label">新密码</span>
              <div className="auth-field__control">
                <span className="auth-field__icon"><Lock size={16} /></span>
                <input
                  type="password"
                  className="pixel-input pixel-input--literal auth-field__input"
                  placeholder="请输入新密码"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                />
              </div>
            </label>

            <label className="auth-field">
              <span className="auth-field__label">确认新密码</span>
              <div className="auth-field__control">
                <span className="auth-field__icon"><KeyRound size={16} /></span>
                <input
                  type="password"
                  className="pixel-input pixel-input--literal auth-field__input"
                  placeholder="再次输入新密码"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                />
              </div>
            </label>

            <div className="auth-footer">{PASSWORD_POLICY_MESSAGE}</div>
            {passwordValidationError && <div className="auth-error">{passwordValidationError}</div>}
            {passwordMismatch && <div className="auth-error">两次输入的密码不一致，请重新确认</div>}
            {error && <div className="auth-error">{error}</div>}
            {success && <div className="auth-success">{success}</div>}

            <button
              type="submit"
              className="pixel-button auth-submit"
              disabled={submitting || !!passwordValidationError || passwordMismatch}
            >
              {submitting ? '重置中...' : '重置密码'}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
