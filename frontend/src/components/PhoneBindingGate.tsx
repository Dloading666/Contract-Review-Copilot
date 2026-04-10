import { useCallback, useState } from 'react'
import { Link2, MessageSquareText, Smartphone } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface PhoneBindingGateProps {
  token: string
  user: User
  onBound: (user: User) => void
  onLogout: () => void
}

export function PhoneBindingGate({ token, user, onBound, onLogout }: PhoneBindingGateProps) {
  const [phone, setPhone] = useState(user.phone ?? '')
  const [code, setCode] = useState('')
  const [devCode, setDevCode] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [sendingCode, setSendingCode] = useState(false)
  const [submitting, setSubmitting] = useState(false)
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

  const handleSendCode = useCallback(async () => {
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

  const handleBind = useCallback(async () => {
    const normalizedPhone = phone.replace(/\D/g, '').slice(-11)
    if (!/^1\d{10}$/.test(normalizedPhone)) {
      setError('请输入有效的 11 位手机号')
      return
    }
    if (!code.trim()) {
      setError('请输入短信验证码')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const response = await fetch('/api/auth/phone/bind', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ phone: normalizedPhone, code: code.trim() }),
      })
      const payload = await response.json() as { error?: string; user?: User }
      if (!response.ok || !payload.user) {
        setError(payload.error || '绑定手机号失败')
        return
      }
      onBound(payload.user)
    } catch {
      setError('网络错误，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }, [code, onBound, phone, token])

  return (
    <div className="auth-shell">
      <div className="auth-card auth-card--narrow">
        <div className="auth-card__form-pane auth-card__form-pane--full">
          <div className="auth-register-copy">
            <h1>先绑定手机号</h1>
            <p>
              你已通过邮箱登录，但当前账户尚未绑定手机号。
              绑定后才能激活 2 次免费完整审查、钱包充值与正式问答权益。
            </p>
          </div>

          <div className="binding-summary">
            <div><strong>当前邮箱：</strong>{user.email || '未设置'}</div>
            <div><strong>免费次数：</strong>绑定手机号后以手机号权益为准</div>
          </div>

          <div className="auth-form">
            <label className="auth-field">
              <span className="auth-field__label">手机号</span>
              <div className="auth-field__control">
                <span className="auth-field__icon"><Smartphone size={16} /></span>
                <input
                  className="pixel-input pixel-input--literal auth-field__input"
                  placeholder="请输入 11 位手机号"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value.replace(/\D/g, '').slice(0, 11))}
                />
              </div>
            </label>

            <div className="auth-code-row">
              <label className="auth-field">
                <span className="auth-field__label">短信验证码</span>
                <div className="auth-field__control">
                  <span className="auth-field__icon"><MessageSquareText size={16} /></span>
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
            {error && <div className="auth-error">{error}</div>}

            <button type="button" className="pixel-button auth-submit" onClick={handleBind} disabled={submitting}>
              <Link2 size={16} />
              {submitting ? '绑定中...' : '绑定手机号并激活权益'}
            </button>

            <button type="button" className="auth-link-button auth-link-button--solo" onClick={onLogout}>
              退出当前账号
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
