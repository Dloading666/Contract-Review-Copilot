import { useState } from 'react'
import { ShieldCheck, Bell, Palette, Monitor, Upload } from 'lucide-react'

interface SettingsPageProps {
  user?: { email: string; id: string } | null
  onBack: () => void
}

export function SettingsPage({ user, onBack }: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState<'personal' | 'security' | 'prefs'>('personal')

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--color-cream)',
      backgroundImage: 'radial-gradient(var(--color-cream-darker) 1.5px, transparent 1.5px)',
      backgroundSize: '20px 20px',
      padding: 32,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{ width: '100%', maxWidth: 800, display: 'flex', flexDirection: 'column', gap: 24 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <img
              src="/doge.png"
              alt="Doge"
              style={{ width: 48, height: 48, border: '4px solid black', objectFit: 'contain', imageRendering: 'pixelated', background: 'white', padding: 2 }}
            />
            <h1 style={{ fontFamily: 'var(--font-header)', fontSize: 14, color: 'var(--color-ink)' }}>
              Doge 合规助手 设置
            </h1>
          </div>
          <button
            className="pixel-button"
            onClick={onBack}
            style={{ background: 'var(--color-blue)', color: 'white' }}
          >
            返回对话
          </button>
        </div>

        {/* Card */}
        <div style={{ border: '4px solid black', boxShadow: '4px 4px 0 rgba(0,0,0,1)', background: 'var(--color-paper)', overflow: 'hidden' }}>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '4px solid black', background: '#f0f0f0' }}>
            {(['personal', 'security', 'prefs'] as const).map((tab, i) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: '16px 32px',
                  fontFamily: 'var(--font-pixel)',
                  fontSize: 9,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  border: 'none',
                  borderRight: i < 2 ? '4px solid black' : 'none',
                  background: activeTab === tab ? 'var(--color-orange)' : 'transparent',
                  color: activeTab === tab ? 'white' : 'var(--color-ink)',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                }}
              >
                {tab === 'personal' ? '个人资料' : tab === 'security' ? '账号安全' : '界面偏好'}
              </button>
            ))}
          </div>

          {/* Content */}
          <div style={{ padding: 32, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 48 }}>
            {/* Left col */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <img
                  src="/doge.png"
                  alt="Avatar"
                  style={{ width: 80, height: 80, border: '4px solid black', objectFit: 'contain', background: 'white', imageRendering: 'pixelated' }}
                />
                <button
                  className="pixel-button"
                  style={{ background: 'var(--color-blue)', color: 'white', display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <Upload size={14} /> 上传头像
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontFamily: 'var(--font-pixel)', fontSize: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-ink-soft)' }}>
                  姓名
                </label>
                <input className="pixel-input" placeholder="像素姓名" />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontFamily: 'var(--font-pixel)', fontSize: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-ink-soft)' }}>
                  邮箱
                </label>
                <input className="pixel-input" placeholder={user?.email || 'wow@doge.com'} disabled />
              </div>
            </div>

            {/* Right col */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              {/* Toggle: 双重验证 */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-pixel)', fontSize: 9, fontWeight: 700 }}>
                  <ShieldCheck size={18} /> 双重验证
                </div>
                <PixelToggle on color="var(--color-blue)" />
              </div>

              {/* Toggle: 邮件通知 */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-pixel)', fontSize: 9, fontWeight: 700 }}>
                  <Bell size={18} /> 邮件通知
                </div>
                <PixelToggle on color="var(--color-green)" />
              </div>

              {/* Slider: 像素缩放 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-pixel)', fontSize: 9, fontWeight: 700 }}>
                  <Palette size={18} /> 像素缩放
                </div>
                <PixelSlider value={75} />
              </div>

              {/* Radio: 主题 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-pixel)', fontSize: 9, fontWeight: 700 }}>
                  <Monitor size={18} /> 主题
                </div>
                <div style={{ display: 'flex', gap: 16 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-pixel)', fontSize: 9, cursor: 'pointer' }}>
                    <input type="radio" name="theme" defaultChecked style={{ width: 14, height: 14, accentColor: 'black' }} /> 亮色
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-pixel)', fontSize: 9, cursor: 'pointer' }}>
                    <input type="radio" name="theme" style={{ width: 14, height: 14, accentColor: 'black' }} /> 暗黑
                  </label>
                </div>
              </div>
            </div>
          </div>

          {/* Footer buttons */}
          <div style={{ padding: '24px 32px', borderTop: '4px solid black', display: 'flex', justifyContent: 'flex-end', gap: 16, background: '#f5f5f5' }}>
            <button className="pixel-button" style={{ padding: '12px 48px', background: 'var(--color-orange)', color: 'white' }}>
              保存设置
            </button>
            <button className="pixel-button" onClick={onBack} style={{ padding: '12px 48px', background: 'var(--color-blue)', color: 'white' }}>
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function PixelToggle({ on, color }: { on: boolean; color: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      background: on ? color : 'var(--color-cream-dark)',
      color: 'white',
      padding: '4px 8px',
      border: '2px solid black',
      fontFamily: 'var(--font-pixel)',
      fontSize: 8,
      fontWeight: 700,
    }}>
      {on ? '开启' : '关闭'}
      <div style={{ width: 14, height: 14, background: 'white', border: '2px solid black' }} />
    </div>
  )
}

function PixelSlider({ value }: { value: number }) {
  const pct = `${value}%`
  return (
    <div style={{ position: 'relative', height: 24, background: '#e0e0e0', border: '4px solid black' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, background: 'var(--color-blue)', width: pct, borderRight: '4px solid black' }} />
      <div style={{
        position: 'absolute',
        left: pct,
        top: '50%',
        transform: 'translate(-50%, -50%)',
        width: 16,
        height: 32,
        background: 'var(--color-orange)',
        border: '4px solid black',
      }} />
    </div>
  )
}
