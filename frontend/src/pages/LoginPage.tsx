import { useCallback, useState } from 'react'
import { motion } from 'motion/react'
import { KeyRound, Lock, Mail, MessageSquareText, Smartphone } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface LoginPageProps {
  onLogin: (token: string, user: User) => void
  onNavigateRegister?: () => void
}

type LoginMode = 'phone' | 'email'

export function LoginPage({ onLogin, onNavigateRegister }: LoginPageProps) {
  const [mode, setMode] = useState<LoginMode>('phone')
  const [phone, setPhone] = useState('')
  const [phoneCode, setPhoneCode] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [devCode, setDevCode] = useState('')
  const [error, setError] = useState('')

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

  const handleSendPhoneCode = useCallback(async () => {
    const normalizedPhone = phone.replace(/\D/g, '').slice(-11)
    if (!/^1\d{10}$/.test(normalizedPhone)) {
      setError('请输入有效的 11 位手机号')
      return
    }

    setSendingCode(true)
    setError('')
    try {
      const response = await fetch('/api/auth/phone/send-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: normalizedPhone }),
      })
      const payload = await response.json() as { error?: string; dev_code?: string }
      if (!response.ok) {
        setError(payload.error || '验证码发送失败')
        return
      }
      setDevCode(payload.dev_code ?? '')
      startCountdown()
    } catch {
      setError('网络错误，请稍后重试')
    } finally {
      setSendingCode(false)
    }
  }, [phone, startCountdown])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')

    try {
      if (mode === 'phone') {
        const normalizedPhone = phone.replace(/\D/g, '').slice(-11)
        if (!/^1\d{10}$/.test(normalizedPhone)) {
          setError('请输入有效的 11 位手机号')
          return
        }
        if (!phoneCode.trim()) {
          setError('请输入短信验证码')
          return
        }

        const response = await fetch('/api/auth/phone/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone: normalizedPhone, code: phoneCode.trim() }),
        })
        const payload = await response.json() as { error?: string; token?: string; user?: User }
        if (!response.ok || !payload.token || !payload.user) {
          setError(payload.error || '手机号登录失败')
          return
        }
        onLogin(payload.token, payload.user)
        return
      }

      if (!email.trim()) {
        setError('请输入邮箱地址')
        return
      }
      if (!password.trim()) {
        setError('请输入密码')
        return
      }

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const payload = await response.json() as { error?: string; token?: string; user?: User }
      if (!response.ok || !payload.token || !payload.user) {
        setError(payload.error || '邮箱登录失败')
        return
      }
      onLogin(payload.token, payload.user)
    } catch {
      setError('网络错误，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-shell">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="auth-card"
      >
        <div className="auth-card__visual">
          <img src="/doge.png" alt="Doge" className="auth-card__doge" />
          <h1 className="auth-card__heading">Doge 合同审查助手</h1>
        </div>

        <div className="auth-card__form-pane">
          <div className="auth-card__tabs">
            <button
              type="button"
              className={`auth-tab${mode === 'phone' ? ' auth-tab--active' : ''}`}
              onClick={() => {
                setMode('phone')
                setError('')
              }}
            >
              <Smartphone size={16} />
              手机号登录
            </button>
            <button
              type="button"
              className={`auth-tab${mode === 'email' ? ' auth-tab--active' : ''}`}
              onClick={() => {
                setMode('email')
                setError('')
              }}
            >
              <Mail size={16} />
              邮箱登录
            </button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === 'phone' ? (
              <>
                <AuthField label="手机号">
                  <span className="auth-field__icon"><Smartphone size={16} /></span>
                  <input
                    className="pixel-input pixel-input--literal auth-field__input"
                    placeholder="请输入 11 位手机号"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value.replace(/\D/g, '').slice(0, 11))}
                  />
                </AuthField>

                <div className="auth-code-row">
                  <AuthField label="短信验证码">
                    <span className="auth-field__icon"><MessageSquareText size={16} /></span>
                    <input
                      className="pixel-input pixel-input--literal auth-field__input"
                      placeholder="请输入 6 位验证码"
                      value={phoneCode}
                      onChange={(event) => setPhoneCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                    />
                  </AuthField>
                  <button
                    type="button"
                    className="pixel-button auth-code-row__button"
                    onClick={handleSendPhoneCode}
                    disabled={sendingCode || countdown > 0}
                  >
                    {countdown > 0 ? `${countdown}s` : sendingCode ? '发送中...' : '获取验证码'}
                  </button>
                </div>
                {devCode && <div className="auth-dev-code">开发模式验证码：{devCode}</div>}
              </>
            ) : (
              <>
                <AuthField label="邮箱地址">
                  <span className="auth-field__icon"><Mail size={16} /></span>
                  <input
                    className="pixel-input pixel-input--literal auth-field__input"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </AuthField>
                <AuthField label="密码">
                  <span className="auth-field__icon"><Lock size={16} /></span>
                  <input
                    type="password"
                    className="pixel-input pixel-input--literal auth-field__input"
                    placeholder="请输入密码"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </AuthField>
              </>
            )}

            {error && <div className="auth-error">{error}</div>}

            <button type="submit" className="pixel-button auth-submit" disabled={loading}>
              <KeyRound size={16} />
              {loading ? '登录中...' : mode === 'phone' ? '手机号登录' : '邮箱登录'}
            </button>
          </form>

          <div className="auth-footer">
            <span>需要一个辅助邮箱账户？</span>
            <button type="button" className="auth-link-button" onClick={onNavigateRegister}>
              去邮箱注册
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

function AuthField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="auth-field">
      <span className="auth-field__label">{label}</span>
      <div className="auth-field__control">{children}</div>
    </label>
  )
}
