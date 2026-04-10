import { useEffect, useState } from 'react'
import { ArrowLeft, BadgeCheck, Mail, Smartphone, Wallet } from 'lucide-react'
import type { User } from '../contexts/AuthContext'
import { WalletRechargeModal } from '../components/WalletRechargeModal'

interface WalletTransaction {
  transaction_id: string
  transaction_type: string
  amount_fen: number
  balance_after_fen: number
  created_at?: string
  description?: string
}

interface RechargeOrder {
  order_id: string
  amount_fen: number
  status: string
  created_at?: string
}

interface SettingsPageProps {
  user: User
  token: string
  onUserUpdate: (user: User) => void
  onBack: () => void
}

function fenToYuan(amountFen: number) {
  return (amountFen / 100).toFixed(amountFen % 100 === 0 ? 0 : 2)
}

export function SettingsPage({ user, token, onUserUpdate, onBack }: SettingsPageProps) {
  const [transactions, setTransactions] = useState<WalletTransaction[]>([])
  const [orders, setOrders] = useState<RechargeOrder[]>([])
  const [showRechargeModal, setShowRechargeModal] = useState(false)

  useEffect(() => {
    let cancelled = false

    const loadSummary = async () => {
      try {
        const response = await fetch('/api/account/summary', {
          headers: { Authorization: `Bearer ${token}` },
        })
        const payload = await response.json() as {
          user?: User
          recentTransactions?: WalletTransaction[]
          recentRechargeOrders?: RechargeOrder[]
        }
        if (!response.ok || cancelled) return
        if (payload.user) onUserUpdate(payload.user)
        if (payload.recentTransactions) setTransactions(payload.recentTransactions)
        if (payload.recentRechargeOrders) setOrders(payload.recentRechargeOrders)
      } catch {
        // Ignore summary refresh errors in the settings shell.
      }
    }

    void loadSummary()
    return () => {
      cancelled = true
    }
  }, [onUserUpdate, token])

  return (
    <div className="account-page">
      <div className="account-page__header">
        <button type="button" className="pixel-button account-page__back" onClick={onBack}>
          <ArrowLeft size={16} />
          返回工作台
        </button>
        <div>
          <h1 className="account-page__title">账户中心</h1>
          <p className="account-page__subtitle">查看手机号绑定状态、剩余免费次数、钱包余额和最近流水。</p>
        </div>
      </div>

      <div className="account-page__grid">
        <section className="account-card">
          <div className="account-card__title">身份信息</div>
          <div className="account-card__list">
            <div className="account-card__row">
              <span className="account-card__label"><Smartphone size={14} /> 手机号</span>
              <span>{user.phone || '未绑定'}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label"><Mail size={14} /> 邮箱</span>
              <span>{user.email || '未设置'}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label"><BadgeCheck size={14} /> 账号状态</span>
              <span>{user.mustBindPhone ? '待绑定手机号' : '已激活'}</span>
            </div>
          </div>
        </section>

        <section className="account-card">
          <div className="account-card__title">权益摘要</div>
          <div className="account-metrics">
            <div className="account-metric">
              <div className="account-metric__value">{user.freeReviewRemaining}</div>
              <div className="account-metric__label">剩余免费完整审查</div>
            </div>
            <div className="account-metric">
              <div className="account-metric__value">¥{fenToYuan(user.walletBalanceFen)}</div>
              <div className="account-metric__label">钱包余额</div>
            </div>
          </div>
          <button type="button" className="pixel-button account-card__cta" onClick={() => setShowRechargeModal(true)}>
            <Wallet size={16} />
            微信扫码充值
          </button>
        </section>

        <section className="account-card account-card--wide">
          <div className="account-card__title">最近钱包流水</div>
          <div className="account-table">
            {transactions.length === 0 ? (
              <div className="account-table__empty">暂无钱包流水</div>
            ) : (
              transactions.map((item) => (
                <div key={item.transaction_id} className="account-table__row">
                  <div>
                    <div className="account-table__main">{item.description || item.transaction_type}</div>
                    <div className="account-table__sub">{item.created_at || ''}</div>
                  </div>
                  <div className={item.amount_fen >= 0 ? 'account-table__amount account-table__amount--positive' : 'account-table__amount account-table__amount--negative'}>
                    {item.amount_fen >= 0 ? '+' : '-'}¥{fenToYuan(Math.abs(item.amount_fen))}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="account-card account-card--wide">
          <div className="account-card__title">最近充值订单</div>
          <div className="account-table">
            {orders.length === 0 ? (
              <div className="account-table__empty">暂无充值订单</div>
            ) : (
              orders.map((order) => (
                <div key={order.order_id} className="account-table__row">
                  <div>
                    <div className="account-table__main">{order.order_id}</div>
                    <div className="account-table__sub">{order.created_at || ''}</div>
                  </div>
                  <div className={`account-order-status account-order-status--${order.status}`}>
                    ¥{fenToYuan(order.amount_fen)} · {order.status}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <WalletRechargeModal
        open={showRechargeModal}
        token={token}
        user={user}
        onClose={() => setShowRechargeModal(false)}
        onUserUpdate={onUserUpdate}
      />
    </div>
  )
}
