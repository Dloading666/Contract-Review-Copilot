import { ArrowLeft, BadgeCheck, Mail } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface SettingsPageProps {
  user: User
  token: string
  onUserUpdate: (user: User) => void
  onBack: () => void
}

export function SettingsPage({ user, onBack }: SettingsPageProps) {
  return (
    <div className="account-page">
      <div className="account-page__header">
        <button type="button" className="pixel-button account-page__back" onClick={onBack}>
          <ArrowLeft size={16} />
          返回工作台
        </button>
        <div>
          <h1 className="account-page__title">账户中心</h1>
          <p className="account-page__subtitle">查看账号基本信息。</p>
        </div>
      </div>

      <div className="account-page__grid">
        <section className="account-card">
          <div className="account-card__title">身份信息</div>
          <div className="account-card__list">
            <div className="account-card__row">
              <span className="account-card__label"><Mail size={14} /> 邮箱</span>
              <span>{user.email || '未设置'}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label"><BadgeCheck size={14} /> 账号状态</span>
              <span>已激活</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
