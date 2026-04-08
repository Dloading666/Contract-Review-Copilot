import { useState, useCallback } from 'react'
import { motion } from 'motion/react'
import { Mail, Lock, ShieldCheck, Eye, EyeOff, CheckCircle2 } from 'lucide-react'

interface RegisterPageProps {
  onNavigateLogin: () => void
}

export function RegisterPage({ onNavigateLogin }: RegisterPageProps) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [devCode, setDevCode] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const hasUpper = /[A-Z]/.test(password)
  const hasLower = /[a-z]/.test(password)
  const hasNumber = /[0-9]/.test(password)
  const hasLength = password.length >= 6
  const passwordsMatch = password === confirmPassword && confirmPassword !== ''

  const sendCode = useCallback(async () => {
    if (!email.trim()) { setError('请输入邮箱地址'); return }
    if (!/^[\w.-]+@[\w.-]+\.\w+$/.test(email.trim())) { setError('请输入有效的邮箱格式'); return }

    setSending(true)
    setError('')
    try {
      const res = await fetch('/api/auth/send-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || '发送失败，请稍后重试'); return }
      if (data.dev_code) setDevCode(data.dev_code)
      setCountdown(60)
      const timer = setInterval(() => {
        setCountdown(c => { if (c <= 1) { clearInterval(timer); return 0 } return c - 1 })
      }, 1000)
    } catch {
      setError('网络错误，请稍后重试')
    } finally {
      setSending(false)
    }
  }, [email])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !code || !password || !confirmPassword) { setError('请填写所有字段'); return }
    if (password !== confirmPassword) { setError('两次密码输入不一致'); return }
    if (password.length < 6) { setError('密码不能少于6位'); return }

    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), code: code.trim(), password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || '注册失败，请重试'); return }
      setSuccess(true)
      setTimeout(() => onNavigateLogin(), 2000)
    } catch {
      setError('网络错误，请检查连接后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      {/* Doge avatar overlapping card */}
      <div style={{ position: 'relative', marginBottom: -44, zIndex: 10 }}>
        <img src="/doge.png" alt="Doge" style={{ width: 88, height: 88, border: '4px solid black', borderRadius: '50%', background: 'white', padding: 4, objectFit: 'contain', imageRendering: 'pixelated' }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ width: '100%', maxWidth: 540, border: '4px solid black', boxShadow: '4px 4px 0px 0px rgba(0,0,0,1)', background: 'var(--color-paper)', padding: '64px 44px 44px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24 }}
      >
        <h1 style={{ fontFamily: 'var(--font-header)', fontSize: 14, color: 'var(--color-ink)', textAlign: 'center', lineHeight: 1.6 }}>
          欢迎注册 Doge 合规助手
        </h1>

        {success ? (
          <div style={{ textAlign: 'center', padding: '24px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
            <CheckCircle2 size={48} color="var(--color-green)" />
            <p style={{ fontFamily: 'var(--font-pixel)', fontSize: 13, fontWeight: 700, color: 'var(--color-green)' }}>注册成功！正在跳转登录…</p>
          </div>
        ) : (
          <form style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 18 }} onSubmit={handleSubmit}>
            {/* Email */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={labelStyle}>电子邮箱</label>
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Mail size={18} style={{ position: 'absolute', left: 12, color: 'var(--color-ink-muted)', pointerEvents: 'none' }} />
                <input type="email" className="pixel-input" placeholder="your@email.com"
                  value={email} onChange={e => setEmail(e.target.value)}
                  style={{ paddingLeft: 44, fontSize: 13 }} />
              </div>
            </div>

            {/* Code row */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={labelStyle}>邮箱验证码</label>
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center' }}>
                  <ShieldCheck size={18} style={{ position: 'absolute', left: 12, color: 'var(--color-ink-muted)', pointerEvents: 'none' }} />
                  <input type="text" className="pixel-input" placeholder="6 位验证码"
                    value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    maxLength={6} style={{ paddingLeft: 44, fontSize: 13 }} />
                </div>
                <button type="button" className="pixel-button" onClick={sendCode}
                  disabled={sending || countdown > 0}
                  style={{ flexShrink: 0, background: 'var(--color-orange)', color: 'white', fontSize: 10, whiteSpace: 'nowrap', padding: '0 16px' }}>
                  {countdown > 0 ? `${countdown}s` : sending ? '发送中…' : '获取验证码'}
                </button>
              </div>
              {devCode && (
                <div style={{ border: '3px solid var(--color-orange)', background: 'var(--color-orange-light)', padding: '8px 12px', fontFamily: 'monospace', fontSize: 12, color: 'var(--color-orange)' }}>
                  开发模式验证码：{devCode}
                </div>
              )}
            </div>

            {/* Password row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={labelStyle}>设置密码</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Lock size={18} style={{ position: 'absolute', left: 12, color: 'var(--color-ink-muted)', pointerEvents: 'none' }} />
                  <input type={showPassword ? 'text' : 'password'} className="pixel-input" placeholder="至少6位"
                    value={password} onChange={e => setPassword(e.target.value)}
                    style={{ paddingLeft: 44, paddingRight: 36, fontSize: 13 }} />
                  <button type="button" onClick={() => setShowPassword(v => !v)}
                    style={{ position: 'absolute', right: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-ink-muted)', display: 'flex', alignItems: 'center' }}>
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={labelStyle}>确认密码</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <Lock size={18} style={{ position: 'absolute', left: 12, color: 'var(--color-ink-muted)', pointerEvents: 'none' }} />
                  <input type={showConfirm ? 'text' : 'password'} className="pixel-input" placeholder="再次输入"
                    value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                    style={{ paddingLeft: 44, paddingRight: 36, fontSize: 13 }} />
                  <button type="button" onClick={() => setShowConfirm(v => !v)}
                    style={{ position: 'absolute', right: 8, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-ink-muted)', display: 'flex', alignItems: 'center' }}>
                    {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
            </div>

            {/* Strength */}
            {password && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                <StrengthRow ok={hasLength} label="至少6位" />
                <StrengthRow ok={hasUpper} label="含大写字母" />
                <StrengthRow ok={hasLower} label="含小写字母" />
                <StrengthRow ok={hasNumber} label="含数字" />
                {confirmPassword && <StrengthRow ok={passwordsMatch} label="密码一致" />}
              </div>
            )}

            {error && (
              <div style={{ border: '3px solid var(--color-red)', background: 'var(--color-red-light)', padding: '10px 14px', fontFamily: 'var(--font-pixel)', fontSize: 10, color: 'var(--color-red)', lineHeight: 1.6 }}>
                {error}
              </div>
            )}

            <button type="submit" className="pixel-button" disabled={loading}
              style={{ width: '100%', padding: '16px 0', fontSize: 16, marginTop: 4, background: 'var(--color-orange)', color: 'white', letterSpacing: '0.05em' }}>
              {loading ? '注册中…' : '立即注册'}
            </button>
          </form>
        )}

        <div style={{ fontFamily: 'var(--font-pixel)', fontSize: 12, textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>
            <span>已有帐号? </span>
            <button type="button" onClick={onNavigateLogin}
              style={{ background: 'none', border: 'none', fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font-pixel)', fontSize: 12, borderBottom: '2px solid black', padding: 0 }}>
              去登录
            </button>
          </div>
          <div style={{ fontFamily: 'var(--font-pixel)', fontSize: 9, color: 'var(--color-ink-muted)' }}>
            © 2024 Doge 合规助手
          </div>
        </div>
      </motion.div>
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  fontFamily: 'var(--font-pixel)',
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: 'var(--color-ink-soft)',
}

function StrengthRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-pixel)', fontSize: 10, fontWeight: 700, color: ok ? '#27ae60' : 'var(--color-ink-muted)' }}>
      <CheckCircle2 size={13} style={{ flexShrink: 0, opacity: ok ? 1 : 0.3 }} />
      {label}
    </div>
  )
}
