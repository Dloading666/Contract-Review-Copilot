import { useEffect, useMemo, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Loader, Wallet, X } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface RechargeOrder {
  order_id: string
  amount_fen: number
  status: string
  code_url: string
  created_at?: string
}

interface WalletRechargeModalProps {
  open: boolean
  token?: string | null
  user: User
  onClose: () => void
  onUserUpdate: (user: User) => void
}

const QUICK_AMOUNT_FEN = 100

function fenToYuan(amountFen: number) {
  return (amountFen / 100).toFixed(amountFen % 100 === 0 ? 0 : 2)
}

export function WalletRechargeModal({
  open,
  token,
  user,
  onClose,
  onUserUpdate,
}: WalletRechargeModalProps) {
  const amountInputRef = useRef<HTMLInputElement | null>(null)
  const [amountInput, setAmountInput] = useState('1')
  const [amountMode, setAmountMode] = useState<'quick' | 'custom'>('quick')
  const [submitting, setSubmitting] = useState(false)
  const [polling, setPolling] = useState(false)
  const [order, setOrder] = useState<RechargeOrder | null>(null)
  const [error, setError] = useState('')

  const amountFen = useMemo(() => {
    const parsed = Number(amountInput)
    if (Number.isNaN(parsed) || parsed <= 0) return 0
    return Math.round(parsed * 100)
  }, [amountInput])

  useEffect(() => {
    if (!open) {
      setAmountInput('1')
      setAmountMode('quick')
      setSubmitting(false)
      setPolling(false)
      setOrder(null)
      setError('')
    }
  }, [open])

  useEffect(() => {
    if (!open || !order || !token || order.status === 'paid') return

    setPolling(true)
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/wallet/recharge/orders/${order.order_id}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        const payload = await response.json() as {
          order?: RechargeOrder
          account?: { user?: User } | User
          error?: string
        }
        if (!response.ok) {
          setError(payload.error || '订单状态查询失败')
          return
        }

        if (payload.order) {
          setOrder(payload.order)
          const accountUser = (payload.account && 'user' in payload.account
            ? payload.account.user
            : payload.account) as User | undefined
          if (payload.order.status === 'paid' && accountUser) {
            onUserUpdate(accountUser)
            clearInterval(timer)
            setPolling(false)
          }
        }
      } catch {
        setError('订单状态查询失败')
      }
    }, 3000)

    return () => {
      clearInterval(timer)
      setPolling(false)
    }
  }, [onUserUpdate, open, order, token])

  if (!open) return null

  const handleSelectCustomAmount = () => {
    setAmountMode('custom')
    amountInputRef.current?.focus()
    amountInputRef.current?.select()
  }

  const handleCreateOrder = async () => {
    if (!token) {
      setError('请先登录后再充值')
      return
    }
    if (amountFen < 100) {
      setError('最低充值金额为 1 元')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const response = await fetch('/api/wallet/recharge/orders', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ amount_fen: amountFen }),
      })
      const payload = await response.json() as {
        order?: RechargeOrder
        error?: string
      }
      if (!response.ok || !payload.order) {
        setError(payload.error || '创建充值订单失败')
        return
      }
      setOrder(payload.order)
    } catch {
      setError('网络错误，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="wallet-modal__backdrop" role="dialog" aria-modal="true" aria-label="钱包充值">
      <div className="wallet-modal">
        <div className="wallet-modal__header">
          <div>
            <div className="wallet-modal__title">钱包充值</div>
            <div className="wallet-modal__subtitle">当前余额：¥{fenToYuan(user.walletBalanceFen)}</div>
          </div>
          <button type="button" className="wallet-modal__close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="wallet-modal__body">
          {!order ? (
            <>
              <div className="wallet-amount-picker">
                <div className="wallet-amount-picker__label">充值金额</div>
                <div className="wallet-amount-picker__quick-list">
                  <button
                    type="button"
                    className={`wallet-amount-chip${amountMode === 'quick' ? ' wallet-amount-chip--active' : ''}`}
                    onClick={() => {
                      setAmountMode('quick')
                      setAmountInput(fenToYuan(QUICK_AMOUNT_FEN))
                    }}
                  >
                    ¥{fenToYuan(QUICK_AMOUNT_FEN)}
                  </button>
                  <button
                    type="button"
                    className={`wallet-amount-chip${amountMode === 'custom' ? ' wallet-amount-chip--active' : ''}`}
                    onClick={handleSelectCustomAmount}
                  >
                    自定义金额
                  </button>
                </div>
                <div className="wallet-amount-picker__input-row">
                  <span>¥</span>
                  <input
                    ref={amountInputRef}
                    className="pixel-input pixel-input--literal wallet-amount-picker__input"
                    value={amountInput}
                    onChange={(event) => {
                      setAmountMode('custom')
                      setAmountInput(event.target.value.replace(/[^\d.]/g, '').slice(0, 8))
                    }}
                    placeholder="1"
                  />
                </div>
                <p className="wallet-amount-picker__hint">支持自定义金额，最低 1 元。每次完整审查扣费 1 元。</p>
              </div>

              {error && <div className="auth-error">{error}</div>}

              <button type="button" className="pixel-button wallet-modal__submit" onClick={handleCreateOrder} disabled={submitting}>
                <Wallet size={16} />
                {submitting ? '创建订单中...' : '微信扫码充值'}
              </button>
            </>
          ) : (
            <div className="wallet-payment-state">
              <div className="wallet-payment-state__amount">应付金额：¥{fenToYuan(order.amount_fen)}</div>
              <div className="wallet-payment-state__qr">
                <QRCodeSVG value={order.code_url} size={200} bgColor="#fff8e8" fgColor="#000" />
              </div>
              <div className="wallet-payment-state__copy">
                请使用微信扫一扫完成充值
                <br />
                订单号：{order.order_id}
              </div>
              <div className={`wallet-payment-state__status wallet-payment-state__status--${order.status}`}>
                {order.status === 'paid' ? '充值成功，余额已到账' : polling ? '等待支付结果...' : '订单已创建'}
              </div>
              {error && <div className="auth-error">{error}</div>}
              {order.status !== 'paid' && (
                <button type="button" className="pixel-button wallet-modal__submit" onClick={handleCreateOrder} disabled={submitting}>
                  {submitting ? <Loader size={16} className="wallet-inline-spinner" /> : <Wallet size={16} />}
                  重新生成二维码
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
