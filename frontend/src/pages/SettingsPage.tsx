import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, BadgeCheck, KeyRound, Mail, ShieldCheck } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface SettingsPageProps {
  user: User
  token: string
  onUserUpdate: (user: User) => void
  onBack: () => void
}

interface PasswordCodeResponse {
  success?: boolean
  dev_code?: string
  error?: string
}

interface PasswordResetResponse {
  success?: boolean
  message?: string
  error?: string
}

function formatAccountStatus(status: string) {
  if (status === 'active') return '已激活'
  if (status === 'disabled') return '已停用'
  return status || '未知'
}

export function SettingsPage({ user, token, onUserUpdate, onBack }: SettingsPageProps) {
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [devCode, setDevCode] = useState('')

  const hasBoundEmail = !!user.email?.trim()
  const canChangePassword = hasBoundEmail && user.hasPassword !== false
  const passwordMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword

  useEffect(() => {
    if (countdown <= 0) return undefined
    const timer = window.setInterval(() => {
      setCountdown((value) => (value > 0 ? value - 1 : 0))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [countdown])

  const sendButtonLabel = useMemo(() => {
    if (isSendingCode) return '发送中...'
    if (countdown > 0) return `${countdown}s 后重试`
    return '发送验证码'
  }, [countdown, isSendingCode])

  const resetForm = () => {
    setCode('')
    setNewPassword('')
    setConfirmPassword('')
    setDevCode('')
  }

  const handleSendCode = async () => {
    if (!hasBoundEmail || isSendingCode || countdown > 0) return

    setIsSendingCode(true)
    setErrorMessage('')
    setSuccessMessage('')
    setDevCode('')

    try {
      const response = await fetch('/api/auth/security/send-password-code', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const payload = await response.json() as PasswordCodeResponse
      if (!response.ok || !payload.success) {
        throw new Error(payload.error || '验证码发送失败，请稍后重试。')
      }

      setSuccessMessage('验证码已发送到当前绑定邮箱，请查收后完成验证。')
      if (payload.dev_code) {
        setDevCode(payload.dev_code)
      }
      setCountdown(60)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '验证码发送失败，请稍后重试。')
    } finally {
      setIsSendingCode(false)
    }
  }

  const handleResetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!hasBoundEmail || isSubmitting) return

    setErrorMessage('')
    setSuccessMessage('')

    if (!code.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      setErrorMessage('请完整填写验证码和新密码。')
      return
    }

    if (newPassword.trim().length < 6) {
      setErrorMessage('新密码不能少于 6 位。')
      return
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage('两次输入的新密码不一致。')
      return
    }

    setIsSubmitting(true)

    try {
      const response = await fetch('/api/auth/security/reset-password', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code: code.trim(),
          new_password: newPassword,
        }),
      })
      const payload = await response.json() as PasswordResetResponse
      if (!response.ok || !payload.success) {
        throw new Error(payload.error || '密码修改失败，请稍后重试。')
      }

      setSuccessMessage(payload.message || '密码修改成功。')
      resetForm()
      onUserUpdate(user)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '密码修改失败，请稍后重试。')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="account-page">
      <div className="account-page__header">
        <button type="button" className="pixel-button account-page__back" onClick={onBack}>
          <ArrowLeft size={16} />
          返回工作台
        </button>
        <div>
          <h1 className="account-page__title">账户中心</h1>
          <p className="account-page__subtitle">查看账号基本信息，并管理登录安全。</p>
        </div>
      </div>

      <div className="account-page__grid">
        <section className="account-card">
          <div className="account-card__title">身份信息</div>
          <div className="account-card__list">
            <div className="account-card__row">
              <span className="account-card__label"><Mail size={14} /> 邮箱</span>
              <span>{user.email || '未绑定'}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label"><BadgeCheck size={14} /> 账号状态</span>
              <span>{formatAccountStatus(user.accountStatus)}</span>
            </div>
          </div>
        </section>

        <section className="account-card account-card--wide">
          <div className="account-card__title">安全中心</div>
          <p className="account-page__subtitle">
            通过当前绑定邮箱获取验证码，验证通过后即可直接重置登录密码。
          </p>

          {!canChangePassword ? (
            <div className="account-security__empty">
              <ShieldCheck size={16} />
              {!hasBoundEmail
                ? '当前账号未绑定邮箱，暂不支持邮箱改密。'
                : '当前账号通过第三方登录（如 GitHub），无需设置密码。'}
            </div>
          ) : (
            <form className="account-security__form" onSubmit={handleResetPassword}>
              <div className="account-security__row">
                <label className="account-security__field">
                  <span className="account-security__label">当前邮箱</span>
                  <div className="account-security__value">
                    <Mail size={14} />
                    <span>{user.email}</span>
                  </div>
                </label>
                <button
                  type="button"
                  className="pixel-button account-card__cta"
                  onClick={handleSendCode}
                  disabled={isSendingCode || countdown > 0}
                >
                  <KeyRound size={14} />
                  {sendButtonLabel}
                </button>
              </div>

              <div className="account-security__inputs">
                <label className="account-security__field">
                  <span className="account-security__label">邮箱验证码</span>
                  <input
                    className="login-input account-security__input"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    placeholder="请输入 6 位验证码"
                    autoComplete="one-time-code"
                  />
                </label>

                <label className="account-security__field">
                  <span className="account-security__label">新密码</span>
                  <input
                    className="login-input account-security__input"
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    placeholder="至少 6 位"
                    autoComplete="new-password"
                  />
                </label>

                <label className="account-security__field">
                  <span className="account-security__label">确认新密码</span>
                  <input
                    className="login-input account-security__input"
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="再次输入新密码"
                    autoComplete="new-password"
                  />
                </label>
              </div>

              {devCode && (
                <p className="account-security__hint" role="status">
                  开发环境验证码：{devCode}
                </p>
              )}
              {passwordMismatch && (
                <p className="account-security__error" role="alert">
                  两次输入的新密码不一致。
                </p>
              )}
              {!!errorMessage && (
                <p className="account-security__error" role="alert">
                  {errorMessage}
                </p>
              )}
              {!!successMessage && (
                <p className="account-security__success" role="status">
                  {successMessage}
                </p>
              )}

              <div className="account-security__actions">
                <button
                  type="submit"
                  className="pixel-button account-security__submit"
                  disabled={isSubmitting || passwordMismatch}
                >
                  {isSubmitting ? '提交中...' : '确认修改密码'}
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}
