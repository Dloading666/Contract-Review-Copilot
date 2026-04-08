import { useState } from 'react'
import { motion } from 'motion/react'
import { Mail, Lock, Eye, EyeOff } from 'lucide-react'

interface LoginPageProps {
  onLogin: (token: string, user: { email: string; id: string }) => void
  onNavigateRegister?: () => void
}

export function LoginPage({ onLogin, onNavigateRegister }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) { setError('请输入邮箱地址'); return }
    if (!password) { setError('请输入密码'); return }

    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || '邮箱或密码错误'); return }
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('auth_user', JSON.stringify(data.user))
      onLogin(data.token, data.user)
    } catch {
      setError('网络错误，请检查连接后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        style={{
          width: '100%',
          maxWidth: 760,
          border: '4px solid black',
          boxShadow: '8px 8px 0px 0px rgba(0,0,0,1)',
          display: 'flex',
          flexDirection: 'row',
          background: 'var(--color-paper)',
          overflow: 'hidden',
        }}
      >
        {/* Form side */}
        <div style={{ flex: 1, padding: '48px 44px', display: 'flex', flexDirection: 'column', gap: 28 }}>
          <div>
            <h1 style={{
              fontFamily: 'var(--font-header)',
              fontSize: 18,
              color: 'var(--color-ink)',
              lineHeight: 1.5,
              marginBottom: 10,
            }}>
              Doge 合规助手登录
            </h1>
            <p style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--color-ink-soft)', lineHeight: 1.6 }}>
              输入邮箱和密码，安全登录
            </p>
          </div>

          <form style={{ display: 'flex', flexDirection: 'column', gap: 20 }} onSubmit={handleSubmit}>
            {/* Email */}
            <Field label="邮箱地址">
              <InputWrap icon={<Mail size={18} />}>
                <input
                  type="email"
                  className="pixel-input pixel-input--literal"
                  placeholder="your@email.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  autoComplete="email"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  style={{ paddingLeft: 44, fontSize: 13 }}
                />
              </InputWrap>
            </Field>

            {/* Password */}
            <Field label="密码">
              <InputWrap icon={<Lock size={18} />} right={
                <button type="button" onClick={() => setShowPassword(v => !v)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 12px', color: 'var(--color-ink-muted)', display: 'flex', alignItems: 'center' }}>
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              }>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="pixel-input pixel-input--literal"
                  placeholder="请输入密码"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete="current-password"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  style={{ paddingLeft: 44, paddingRight: 44, fontSize: 13 }}
                />
              </InputWrap>
            </Field>

            {/* Remember / forgot */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 700 }}>
                <input type="checkbox" style={{ width: 16, height: 16, border: '2px solid black', accentColor: 'black' }} />
                记住我
              </label>
              <span style={{ fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 700, borderBottom: '2px solid black', cursor: 'pointer' }}>
                忘记密码?
              </span>
            </div>

            {error && (
              <div style={{ border: '3px solid var(--color-red)', background: 'var(--color-red-light)', padding: '10px 14px', fontFamily: 'var(--font-ui)', fontSize: 10, color: 'var(--color-red)', lineHeight: 1.6 }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="pixel-button"
              disabled={loading}
              style={{ width: '100%', padding: '16px 0', fontSize: 16, marginTop: 4, background: 'var(--color-green)', color: 'white', fontFamily: 'var(--font-ui)', textTransform: 'none', letterSpacing: 'normal' }}
            >
              {loading ? <span style={{ width: 18, height: 18, border: '3px solid rgba(255,255,255,0.4)', borderTopColor: 'white', display: 'inline-block', animation: 'login-spin 0.6s steps(4) infinite' }} /> : '安全登录'}
            </button>
          </form>

          <div style={{ fontFamily: 'var(--font-ui)', fontSize: 12, textAlign: 'center', marginTop: 4 }}>
            <span>没有帐号? </span>
            <button type="button" onClick={onNavigateRegister}
              style={{ background: 'none', border: 'none', fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font-ui)', fontSize: 12, borderBottom: '2px solid black', padding: 0 }}>
              立即注册
            </button>
          </div>
        </div>

        {/* Doge side */}
        <div style={{ width: '36%', background: 'var(--color-cream-darker)', borderLeft: '4px solid black', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <img src="/doge.png" alt="Doge" style={{ width: '100%', height: 'auto', objectFit: 'contain', imageRendering: 'pixelated' }} />
        </div>
      </motion.div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 700, textTransform: 'none', letterSpacing: 'normal', color: 'var(--color-ink-soft)' }}>
        {label}
      </label>
      {children}
    </div>
  )
}

function InputWrap({ icon, right, children }: { icon: React.ReactNode; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      <span style={{ position: 'absolute', left: 12, color: 'var(--color-ink-muted)', pointerEvents: 'none', display: 'flex', alignItems: 'center', zIndex: 1 }}>{icon}</span>
      <div style={{ flex: 1 }}>{children}</div>
      {right && <span style={{ position: 'absolute', right: 0, display: 'flex', alignItems: 'center', height: '100%' }}>{right}</span>}
    </div>
  )
}
