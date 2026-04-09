import { useState } from 'react'
import { AlertTriangle, ShieldAlert } from 'lucide-react'

interface DisclaimerModalProps {
  onAccept: () => void
}

export function DisclaimerModal({ onAccept }: DisclaimerModalProps) {
  const [checked, setChecked] = useState(false)

  return (
    <div className="disclaimer-backdrop">
      <div
        className="disclaimer-modal pixel-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="disclaimer-title"
      >
        <div className="disclaimer-modal__badge">
          <ShieldAlert size={18} />
          使用前须知
        </div>

        <h1 id="disclaimer-title" className="disclaimer-modal__title">
          免责声明
        </h1>

        <div className="disclaimer-modal__body">
          <p>
            本网站仅提供合同风险扫描、条款提示和辅助说明，内容仅供参考，不构成正式法律意见、律师建议或任何结果保证。
          </p>
          <p>
            用户应结合合同原文、自身情况及专业法律服务独立判断和决策。因依赖本网站内容而产生的争议、损失或其他后果，
            由用户自行承担，本网站及运营方不承担责任。
          </p>
        </div>

        <div className="disclaimer-modal__notice">
          <AlertTriangle size={18} />
          当前账号确认一次后，本浏览器下次使用该账号时将自动记住。
        </div>

        <label className="disclaimer-modal__checkbox">
          <input
            type="checkbox"
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
          />
          <span>我已知悉并同意上述免责声明</span>
        </label>

        <button
          type="button"
          className="pixel-button disclaimer-modal__button"
          disabled={!checked}
          onClick={onAccept}
        >
          同意并继续
        </button>
      </div>
    </div>
  )
}
