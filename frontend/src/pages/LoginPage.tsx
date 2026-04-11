import { useState, type SyntheticEvent } from 'react'
import { motion } from 'motion/react'
import { Github, KeyRound, Lock, Mail } from 'lucide-react'
import type { User } from '../contexts/AuthContext'
import dogeImage from '../assets/branding/doge.png'

interface LoginPageProps {
  onLogin: (token: string, user: User) => void
  onNavigateRegister?: () => void
  onNavigateLanding?: () => void
}

function handleDogeImageError(event: SyntheticEvent<HTMLImageElement>) {
  const image = event.currentTarget
  if (image.dataset.fallbackApplied === 'true') return
  image.dataset.fallbackApplied = 'true'
  image.src = '/doge.png'
}

export function LoginPage({ onLogin, onNavigateRegister, onNavigateLanding }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')

    if (!email.trim()) {
      setError('请输入邮箱地址')
      return
    }
    if (!password.trim()) {
      setError('请输入密码')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })
      const payload = await response.json() as { error?: string; token?: string; user?: User }
      if (!response.ok || !payload.token || !payload.user) {
        setError(payload.error || '邮箱或密码错误')
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
          <img src={dogeImage} alt="Doge" className="auth-card__doge" onError={handleDogeImageError} />
          <h1 className="auth-card__heading">Doge 合同审查助手</h1>
        </div>

        <div className="auth-card__form-pane">
          <button
            type="button"
            className="auth-back-to-landing"
            onClick={onNavigateLanding}
          >
            ← 返回首页
          </button>

          <form className="auth-form" onSubmit={handleSubmit}>
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

            {error && <div className="auth-error">{error}</div>}

            <button type="submit" className="pixel-button auth-submit" disabled={loading}>
              <KeyRound size={16} />
              {loading ? '登录中...' : '邮箱登录'}
            </button>
          </form>

          <div className="auth-divider">或</div>

          <button
            type="button"
            className="pixel-button auth-github-button"
            onClick={() => { window.location.href = '/api/auth/github' }}
          >
            <Github size={16} />
            GitHub 登录
          </button>

          <div className="auth-footer">
            <span>还没有账户？</span>
            <button type="button" className="auth-link-button" onClick={onNavigateRegister}>
              邮箱注册
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
