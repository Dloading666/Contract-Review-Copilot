import { useEffect } from 'react'

interface LandingPageProps {
  onNavigateLogin: () => void
  onNavigateRegister: () => void
}

export function LandingPage({ onNavigateLogin, onNavigateRegister }: LandingPageProps) {
  useEffect(() => {
    // Inject landing page specific styles to override global CSS
    const styleId = 'landing-page-override'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = `
        body {
          font-family: 'Work Sans', sans-serif !important;
          background-color: #f7f7f2 !important;
          background-image: none !important;
          overflow: auto !important;
          -webkit-font-smoothing: antialiased !important;
        }
        #root {
          height: auto !important;
          overflow: visible !important;
        }
        h1, h2, h3, h4 {
          font-family: 'Space Grotesk', sans-serif !important;
        }
      `
      document.head.appendChild(style)
    }
    return () => {
      const style = document.getElementById(styleId)
      if (style) style.remove()
    }
  }, [])

  return (
    <div style={{ color: '#2d2f2c', backgroundColor: '#f7f7f2', minHeight: '100vh' }}>
      {/* TopNavBar */}
      <header style={{ position: 'sticky', top: 0, zIndex: 50, width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 32px', backgroundColor: '#f7f7f2', borderBottom: '3px solid #2d2f2c' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.02em', color: '#2d2f2c', fontFamily: "'Space Grotesk', sans-serif" }}>
          合同审查全能扫描
        </div>
        <nav style={{ display: 'flex', gap: '32px', alignItems: 'center' }}>
          <a href="#" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, color: '#006a35', borderBottom: '4px solid #006a35' }}> </a>
          <a href="#" style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, color: '#2d2f2c' }}> </a>
        </nav>
        <div style={{ display: 'flex', gap: '16px' }}>
          <button
            onClick={onNavigateLogin}
            style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, padding: '8px 24px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', backgroundColor: '#f7f7f2', color: '#2d2f2c', textTransform: 'uppercase', fontSize: '0.875rem', cursor: 'pointer' }}
          >
            登录
          </button>
          <button
            onClick={onNavigateRegister}
            style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, padding: '8px 24px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', backgroundColor: '#006a35', color: '#cdffd4', textTransform: 'uppercase', fontSize: '0.875rem', cursor: 'pointer' }}
          >
            免费注册
          </button>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section style={{ position: 'relative', padding: '80px 32px', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '64px', overflow: 'hidden' }}>
          <div style={{ flex: 1, zIndex: 10 }}>
            <div style={{ display: 'inline-block', padding: '4px 16px', border: '3px solid #2d2f2c', backgroundColor: '#ffc787', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontSize: '0.875rem' }}>
              100%免费哦
            </div>
            <h1 style={{ fontSize: '3rem', fontWeight: 700, lineHeight: 1, letterSpacing: '-0.02em', textTransform: 'uppercase', marginTop: '32px', fontFamily: "'Space Grotesk', sans-serif" }}>
              AI 智能合同审查<br />
              <span style={{ color: '#006a35', fontStyle: 'italic' }}>免费使用 规避风险</span>
            </h1>
            <p style={{ fontSize: '1.25rem', maxWidth: '36rem', color: '#5a5c58', marginTop: '24px', fontFamily: "'Work Sans', sans-serif" }}>
              像架构师一样构建契约。Doge Draftsman 利用先进 AI 技术，秒级识别合同漏洞。现在完全免费，为您节省 100% 的法务审查费用。
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', marginTop: '16px' }}>
              <button
                onClick={onNavigateRegister}
                style={{ padding: '20px 40px', fontSize: '1.25rem', fontWeight: 700, backgroundColor: '#6bfe9c', color: '#005f2f', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', textTransform: 'uppercase', letterSpacing: '-0.01em', cursor: 'pointer', fontFamily: "'Space Grotesk', sans-serif" }}
              >
                立即免费开始
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px 24px', backgroundColor: '#dcddd7', border: '3px solid #2d2f2c' }}>
                <span className="material-symbols-outlined" style={{ fontSize: '1.5rem', color: '#006a35' }}>verified_user</span>
                <span style={{ fontWeight: 700, fontSize: '0.875rem' }}>100% 隐私安全加密</span>
              </div>
            </div>
          </div>

          <div style={{ flex: 1, position: 'relative' }}>
            <div style={{ width: '100%', aspectRatio: '1', backgroundColor: '#ffc787', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', position: 'relative' }}>
              <img
                alt="Doge Architect"
                style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'grayscale(100%) contrast(125%)', imageRendering: 'pixelated' }}
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuBPs6it5Z0wSQss3C0ez_kvP45EYg9L4YnB7uNqnjDl72k30dX8XmN9hbwxv0NsXh8JRZCRt9vRGt18BDsyQnJWmPGkiDlBr9FV52ivd7PbK2Ej4cG8zDTMyHM7A0zIzfj2AooADb2-nPdsz8wXjvm7kqOy6sEo1qir4SqXM1M0MyCqUnml5qPUXlAKFJoIZqW1L6K32lfHleOCDqD7nVbUJfJ1YCQeFIWlGcEwl0AQNiSCZ0UACMj7F-18tftfw0t2jGyPXyhH14o"
              />
              <div style={{ position: 'absolute', bottom: '-32px', left: '-32px', backgroundColor: '#f7f7f2', border: '3px solid #2d2f2c', padding: '24px', maxWidth: '320px', transform: 'rotate(3deg)', boxShadow: '4px 4px 0px 0px #2d2f2c' }}>
                <p style={{ fontWeight: 700, fontSize: '1.125rem', lineHeight: 1.4 }}>"审查速度太快了，而且居然是免费的！"</p>
                <p style={{ fontSize: '0.875rem', marginTop: '8px', opacity: 0.7 }}>— 某独角兽公司法务总监</p>
              </div>
            </div>
          </div>

          {/* Decorative Background */}
          <div style={{ position: 'absolute', top: 0, right: 0, zIndex: 0, opacity: 0.1, pointerEvents: 'none' }}>
            <div style={{ fontSize: '20rem', fontWeight: 900, lineHeight: 1, userSelect: 'none' }}>FREE</div>
          </div>
        </section>

        {/* Features Section */}
        <section style={{ padding: '96px 32px', backgroundColor: '#f1f1ec', borderTop: '5px solid #2d2f2c', borderBottom: '5px solid #2d2f2c' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '32px', maxWidth: '1200px', margin: '0 auto' }}>
            {/* Card 1 */}
            <div style={{ backgroundColor: '#f7f7f2', padding: '40px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div style={{ width: '64px', height: '64px', backgroundColor: '#6bfe9c', border: '3px solid #2d2f2c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className="material-symbols-outlined" style={{ fontSize: '2rem' }} data-weight="fill">bolt</span>
              </div>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '-0.01em', fontFamily: "'Space Grotesk', sans-serif" }}>秒级风险扫描</h3>
              <p style={{ color: '#5a5c58', fontFamily: "'Work Sans', sans-serif" }}>采用毫秒级响应引擎，上传即分析。自动识别显失公平、违约责任模糊等 50+ 类合同风险。</p>
            </div>
            {/* Card 2 */}
            <div style={{ backgroundColor: '#f7f7f2', padding: '40px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', display: 'flex', flexDirection: 'column', gap: '24px', transform: 'translateY(-16px)' }}>
              <div style={{ width: '64px', height: '64px', backgroundColor: '#ffc787', border: '3px solid #2d2f2c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className="material-symbols-outlined" style={{ fontSize: '2rem' }} data-weight="fill">find_in_page</span>
              </div>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '-0.01em', fontFamily: "'Space Grotesk', sans-serif" }}>条款逐条解析</h3>
              <p style={{ color: '#5a5c58', fontFamily: "'Work Sans', sans-serif" }}>不仅仅是纠错。我们会为每一项关键条款提供深度解读，确保您完全理解协议背后的法律含义。</p>
            </div>
            {/* Card 3 */}
            <div style={{ backgroundColor: '#f7f7f2', padding: '40px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div style={{ width: '64px', height: '64px', backgroundColor: '#5cb8fd', border: '3px solid #2d2f2c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className="material-symbols-outlined" style={{ fontSize: '2rem' }} data-weight="fill">gavel</span>
              </div>
              <h3 style={{ fontSize: '1.5rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '-0.01em', fontFamily: "'Space Grotesk', sans-serif" }}>合规性建议</h3>
              <p style={{ color: '#5a5c58', fontFamily: "'Work Sans', sans-serif" }}>根据最新民法典及行业标准，针对漏洞提供精准修改建议，直接复制粘贴，完全免费不限次。</p>
            </div>
          </div>
        </section>

        {/* How It Works */}
        <section style={{ padding: '96px 32px', backgroundColor: '#f7f7f2' }}>
          <h2 style={{ fontSize: '2.25rem', fontWeight: 700, textTransform: 'uppercase', textAlign: 'center', marginBottom: '80px', letterSpacing: '-0.02em', fontFamily: "'Space Grotesk', sans-serif" }}>三个步骤，掌控契约</h2>
          <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: '48px', maxWidth: '72rem', margin: '0 auto' }}>
            {/* Step 01 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '24px' }}>
              <div style={{ width: '96px', height: '96px', borderRadius: '50%', border: '4px solid #2d2f2c', backgroundColor: '#e8e9e3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2.25rem', fontWeight: 700, boxShadow: '4px 4px 0px 0px #2d2f2c', fontFamily: "'Space Grotesk', sans-serif" }}>
                01
              </div>
              <div>
                <h4 style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase', fontFamily: "'Space Grotesk', sans-serif" }}>上传合同</h4>
                <p style={{ color: '#5a5c58', marginTop: '8px', fontFamily: "'Work Sans', sans-serif" }}>支持 PDF, Word, 图片等<br />多种格式</p>
              </div>
            </div>
            <div style={{ width: '96px', height: '3px', backgroundColor: '#2d2f2c', display: 'none' }} className="md:block" />
            {/* Step 02 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '24px' }}>
              <div style={{ width: '96px', height: '96px', borderRadius: '50%', border: '4px solid #2d2f2c', backgroundColor: '#e8e9e3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2.25rem', fontWeight: 700, boxShadow: '4px 4px 0px 0px #2d2f2c', fontFamily: "'Space Grotesk', sans-serif" }}>
                02
              </div>
              <div>
                <h4 style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase', fontFamily: "'Space Grotesk', sans-serif" }}>智能分析</h4>
                <p style={{ color: '#5a5c58', marginTop: '8px', fontFamily: "'Work Sans', sans-serif" }}>AI 引擎深度检索<br />每一行文字</p>
              </div>
            </div>
            <div style={{ width: '96px', height: '3px', backgroundColor: '#2d2f2c' }} className="hidden md:block" />
            {/* Step 03 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '24px' }}>
              <div style={{ width: '96px', height: '96px', borderRadius: '50%', border: '4px solid #2d2f2c', backgroundColor: '#e8e9e3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2.25rem', fontWeight: 700, boxShadow: '4px 4px 0px 0px #2d2f2c', fontFamily: "'Space Grotesk', sans-serif" }}>
                03
              </div>
              <div>
                <h4 style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase', fontFamily: "'Space Grotesk', sans-serif" }}>获取建议</h4>
                <p style={{ color: '#5a5c58', marginTop: '8px', fontFamily: "'Work Sans', sans-serif" }}>生成完整报告并<br />提供修改意见</p>
              </div>
            </div>
          </div>
        </section>

        {/* AI Framework Section */}
        <section style={{ padding: '96px 32px', backgroundColor: '#e8e9e3', borderTop: '5px solid #2d2f2c' }}>
          <div style={{ maxWidth: '72rem', margin: '0 auto', backgroundColor: '#f7f7f2', padding: '32px 48px', border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', position: 'relative' }}>
            <div style={{ position: 'absolute', top: 0, right: 0, backgroundColor: '#006a35', color: '#cdffd4', padding: '4px 16px', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              Technology Source
            </div>
            <div style={{ display: 'flex', flexDirection: 'row', gap: '48px', alignItems: 'center' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', minWidth: '200px' }}>
                <div style={{ width: '96px', height: '96px', backgroundColor: '#2d2f2c', padding: '16px', boxShadow: '4px 4px 0px 0px #6bfe9c', border: '3px solid #2d2f2c' }}>
                  <svg style={{ width: '100%', height: '100%', fill: 'white' }} viewBox="0 0 24 24">
                    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
                  </svg>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <a href="#" style={{ color: '#006a35', fontWeight: 700, textDecoration: 'underline', fontSize: '0.875rem', display: 'block' }}>claude-legal-skill</a>
                  <span style={{ color: '#5a5c58', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>(Community Version)</span>
                </div>
              </div>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <h2 style={{ fontSize: '2rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '-0.02em', fontFamily: "'Space Grotesk', sans-serif" }}>由业界领先的法律 AI 框架驱动</h2>
                <p style={{ fontSize: '1.125rem', color: '#5a5c58', fontFamily: "'Work Sans', sans-serif" }}>
                  Doge Draftsman 的核心服务基于开源社区版 <span style={{ backgroundColor: '#ffc787', border: '2px solid #2d2f2c', padding: '0 8px' }}>claude-legal-skill</span>，我们深耕底层技术，为每一份合同保驾护航。
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                  <div style={{ border: '3px solid #2d2f2c', padding: '16px', backgroundColor: '#f1f1ec' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#5a5c58', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>数据源</span>
                    <span style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase' }}>CUAD 数据集</span>
                  </div>
                  <div style={{ border: '3px solid #2d2f2c', padding: '16px', backgroundColor: '#f1f1ec' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#5a5c58', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>训练规模</span>
                    <span style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase' }}>510 份真实法律合同</span>
                  </div>
                  <div style={{ gridColumn: 'span 2', border: '3px solid #2d2f2c', padding: '16px', backgroundColor: '#f1f1ec' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#5a5c58', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>风险覆盖</span>
                    <span style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase' }}>41 类核心法律风险识别</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Disclaimer Module */}
        <section style={{ padding: '48px 32px', backgroundColor: '#e8e9e3' }}>
          <div style={{ maxWidth: '72rem', margin: '0 auto' }}>
            <div style={{ border: '4px solid #2d2f2c', backgroundColor: '#fff9e6', padding: '24px 32px', display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: '24px', boxShadow: '4px 4px 0px 0px #2d2f2c' }}>
              <div style={{ width: '48px', height: '48px', backgroundColor: '#ffc787', border: '3px solid #2d2f2c', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '2px 2px 0px 0px #2d2f2c', flexShrink: 0 }}>
                <span className="material-symbols-outlined" style={{ fontSize: '1.75rem', color: '#4c2d00' }}>warning</span>
              </div>
              <div style={{ flex: 1, textAlign: 'left' }}>
                <p style={{ fontSize: '1rem', fontWeight: 700, lineHeight: 1.6, color: '#2d2f2c' }}>
                  <span style={{ textTransform: 'uppercase', letterSpacing: '-0.01em', borderBottom: '2px solid #2d2f2c', marginRight: '8px' }}>免责声明：</span>
                  本网页提供的所有信息及审查结果仅供参考，不构成任何形式的法律建议或专业意见。用户在使用本工具时应自行承担相应风险，建议在处理重要法律事务时咨询专业律师。
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Testimonials */}
        <section style={{ padding: '96px 32px', backgroundColor: '#2d2f2c', color: '#f7f7f2', borderTop: '5px solid #2d2f2c' }}>
          <div style={{ maxWidth: '80rem', margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '64px' }}>
            <div style={{ position: 'relative' }}>
              <div style={{ backgroundColor: '#f7f7f2', color: '#2d2f2c', padding: '32px', border: '3px solid #dcddd7', boxShadow: '4px 4px 0px 0px #2d2f2c', position: 'relative' }}>
                <p style={{ fontSize: '1.25rem', fontWeight: 600, fontStyle: 'italic' }}>"作为一名独立开发者，我总是担心签署那些复杂的合同。Doge Draftsman 帮我找出了两个隐藏的赔偿陷阱，而且完全免费！"</p>
                <div style={{ position: 'absolute', bottom: '-16px', left: '40px', width: '32px', height: '32px', backgroundColor: '#f7f7f2', borderRight: '3px solid #dcddd7', borderBottom: '3px solid #dcddd7', transform: 'rotate(45deg)' }} />
              </div>
              <div style={{ marginTop: '32px', display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ width: '48px', height: '48px', backgroundColor: '#006a35', border: '2px solid #f7f7f2' }} />
                <div>
                  <p style={{ fontWeight: 700 }}>李先生</p>
                  <p style={{ fontSize: '0.875rem', opacity: 0.6 }}>独立开发者</p>
                </div>
              </div>
            </div>
            <div style={{ position: 'relative', marginTop: '96px' }}>
              <div style={{ backgroundColor: '#f7f7f2', color: '#2d2f2c', padding: '32px', border: '3px solid #dcddd7', boxShadow: '4px 4px 0px 0px #2d2f2c', position: 'relative' }}>
                <p style={{ fontSize: '1.25rem', fontWeight: 600, fontStyle: 'italic' }}>"审查效率提升了至少 5 倍。不可思议的是，这种级别的 AI 服务竟然是免费提供的。"</p>
                <div style={{ position: 'absolute', bottom: '-16px', left: '40px', width: '32px', height: '32px', backgroundColor: '#f7f7f2', borderRight: '3px solid #dcddd7', borderBottom: '3px solid #dcddd7', transform: 'rotate(45deg)' }} />
              </div>
              <div style={{ marginTop: '32px', display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ width: '48px', height: '48px', backgroundColor: '#825000', border: '2px solid #f7f7f2' }} />
                <div>
                  <p style={{ fontWeight: 700 }}>张女士</p>
                  <p style={{ fontSize: '0.875rem', opacity: 0.6 }}>初创公司合伙人</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <section style={{ margin: '0 32px 96px 32px', padding: '64px', backgroundColor: '#ffc787', border: '3px solid #2d2f2c', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '32px', boxShadow: '4px 4px 0px 0px #2d2f2c' }}>
          <h2 style={{ fontSize: '3rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '-0.02em', maxWidth: '48rem', fontFamily: "'Space Grotesk', sans-serif" }}>
            别让法律漏洞<br />毁掉你的生意
          </h2>
          <p style={{ fontSize: '1.25rem', fontWeight: 700, maxWidth: '36rem', opacity: 0.8 }}>体验 0 成本、高效率的 AI 合同合规审查</p>
          <div style={{ display: 'flex', flexDirection: 'row', gap: '24px', marginTop: '16px' }}>
            <button
              onClick={onNavigateRegister}
              style={{ padding: '24px 48px', backgroundColor: '#2d2f2c', color: '#f7f7f2', fontSize: '1.5rem', fontWeight: 700, border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', textTransform: 'uppercase', letterSpacing: '-0.01em', cursor: 'pointer', fontFamily: "'Space Grotesk', sans-serif" }}
            >
              立即免费试用
            </button>
            <button
              onClick={onNavigateRegister}
              style={{ padding: '24px 48px', backgroundColor: '#f7f7f2', color: '#2d2f2c', fontSize: '1.5rem', fontWeight: 700, border: '3px solid #2d2f2c', boxShadow: '4px 4px 0px 0px #2d2f2c', textTransform: 'uppercase', letterSpacing: '-0.01em', cursor: 'pointer', fontFamily: "'Space Grotesk', sans-serif" }}
            >
              进行注册
            </button>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer style={{ width: '100%', padding: '48px 32px', display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: '24px', backgroundColor: '#2d2f2c', borderTop: '5px solid #2d2f2c', flexWrap: 'wrap' }}>
        <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f7f7f2' }}>© 2026 ANALOG ARCHITECT. 保留所有权利。</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '32px' }}>
          <a href="#" style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#dcddd7' }}>隐私政策</a>
          <a href="#" style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#dcddd7' }}>服务条款</a>
          <a href="#" style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#dcddd7' }}>联系我们</a>
        </div>
        <div style={{ color: '#6bfe9c', fontFamily: "'Space Grotesk', sans-serif", fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', backgroundColor: 'rgba(255,255,255,0.1)', padding: '8px 16px' }}>
          为所有法律专业人士和开发者免费提供
        </div>
      </footer>
    </div>
  )
}
