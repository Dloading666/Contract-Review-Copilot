import { useCallback, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Mail, ShieldCheck } from 'lucide-react'
import { safeFetchJSON } from '../lib/apiClient'
import { apiPath } from '../lib/apiPaths'
import { getPasswordValidationError, PASSWORD_POLICY_MESSAGE } from '../lib/passwordPolicy'

function buildClientElapsed(startedAt: number) {
  return Math.max(0, Date.now() - startedAt)
}

interface RegisterPageProps {
  onNavigateLogin: () => void
}

export function RegisterPage({ onNavigateLogin }: RegisterPageProps) {
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
  const interactionStartedAt = useMemo(() => Date.now(), [])
  const passwordValidationError = password ? getPasswordValidationError(password) : null

  const startCountdown = useCallback(() => {
    setCountdown(60)
    const timer = setInterval(() => {
      setCountdown((value) => {
        if (value <= 1) {
          clearInterval(timer)
          return 0
        }
        return value - 1
      })
    }, 1000)
  }, [])

  const handleSendCode = useCallback(async () => {
    if (!email.trim()) {
      setError('请输入邮箱地址')
      return
    }

    setSendingCode(true)
    setError('')
    try {
      const payload = await safeFetchJSON<{ error?: string; dev_code?: string }>(apiPath('/auth/send-code'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          website: '',
          client_elapsed_ms: buildClientElapsed(interactionStartedAt),
          captcha_token: null,
        }),
      })
      setDevCode(payload.dev_code ?? '')
      startCountdown()
    } catch (err) {
      setError(err instanceof Error ? err.message : '网络错误，请稍后重试')
    } finally {
      setSendingCode(false)
    }
  }, [email, startCountdown])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!email.trim() || !code.trim() || !password.trim() || !confirmPassword.trim()) {
      setError('请填写完整信息')
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
      await safeFetchJSON(apiPath('/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          code: code.trim(),
          password,
          website: '',
          client_elapsed_ms: buildClientElapsed(interactionStartedAt),
          captcha_token: null,
        }),
      })
      setSuccess('注册成功！即将跳转到登录页...')
      setTimeout(() => onNavigateLogin(), 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败')
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
            <h1>邮箱注册</h1>
            <p>注册邮箱账户后即可登录使用合同审查功能。</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <input type="text" name="website" autoComplete="off" tabIndex={-1} style={{ display: 'none' }} aria-hidden="true" />
            <label className="auth-field">
              <span className="auth-field__label">邮箱地址</span>
              <div className="auth-field__control">
                <span className="auth-field__icon"><Mail size={16} /></span>
                <input
                  className="pixel-input pixel-input--literal auth-field__input"
                  placeholder="name@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
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
              <span className="auth-field__label">登录密码</span>
              <div className="auth-field__control">
                <input
                  type="password"
                  className="pixel-input pixel-input--literal auth-field__input auth-field__input--plain"
                  placeholder="请输入登录密码"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </label>

            <label className="auth-field">
              <span className="auth-field__label">确认密码</span>
              <div className="auth-field__control">
                <input
                  type="password"
                  className="pixel-input pixel-input--literal auth-field__input auth-field__input--plain"
                  placeholder="再次输入密码"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              </div>
            </label>

            <div className="auth-footer">{PASSWORD_POLICY_MESSAGE}</div>
            {passwordValidationError && <div className="auth-error">{passwordValidationError}</div>}
            {error && <div className="auth-error">{error}</div>}
            {success && <div className="auth-success">{success}</div>}

            <button type="submit" className="pixel-button auth-submit" disabled={submitting || !!passwordValidationError}>
              {submitting ? '注册中...' : '创建邮箱账户'}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
