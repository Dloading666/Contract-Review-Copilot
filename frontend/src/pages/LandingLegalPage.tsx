import { useEffect } from 'react'
import { Github } from 'lucide-react'

import '../styles/landing.css'

type LegalPageVariant = 'privacy' | 'terms'

interface LandingLegalPageProps {
  variant: LegalPageVariant
  onNavigateLanding: () => void
  onNavigateLogin: () => void
  onNavigateRegister: () => void
}

const GITHUB_REPOSITORY_URL = 'https://github.com/Dloading666/Contract-Review-Copilot'
const GITHUB_ISSUES_URL = `${GITHUB_REPOSITORY_URL}/issues`

const pageCopy = {
  privacy: {
    eyebrow: 'Privacy Policy',
    title: '隐私政策',
    intro: '我们把合同文本、图片和登录信息都视为敏感数据处理，只围绕合同审查、报告导出和账号安全使用。',
    sections: [
      {
        title: '我们会处理哪些数据',
        body: '你上传的合同文本、图片 OCR 结果、审查过程中的风险项、问答内容，以及登录所需的邮箱或第三方授权信息。',
      },
      {
        title: '这些数据如何使用',
        body: '数据只用于完成合同解析、风险识别、报告生成、历史记录恢复和必要的服务安全校验，不会在页面上公开展示给其他用户。',
      },
      {
        title: '你需要注意什么',
        body: '请避免上传与合同审查无关的身份证号、银行卡号、病历等高敏感信息；如果合同里包含这些内容，建议先脱敏后再上传。',
      },
    ],
  },
  terms: {
    eyebrow: 'Terms of Service',
    title: '服务条款',
    intro: 'CTSafe 是合同风险辅助审查工具，帮助用户快速定位潜在风险，但不替代律师、仲裁机构或法院的专业判断。',
    sections: [
      {
        title: '服务定位',
        body: '系统输出的风险提示、法律依据和修改建议仅供参考，不构成正式法律意见；重要交易或争议建议再咨询专业律师。',
      },
      {
        title: '用户责任',
        body: '你需要确保上传材料来源合法，并自行判断 AI 输出是否适用于具体合同场景；不要将平台用于违法、侵权或恶意用途。',
      },
      {
        title: '反馈与维护',
        body: '如果发现识别错误、报告异常或安全问题，可以通过 GitHub Issues 联系维护者，我们会优先处理影响正常使用的问题。',
      },
    ],
  },
} as const

export function LandingLegalPage({
  variant,
  onNavigateLanding,
  onNavigateLogin,
  onNavigateRegister,
}: LandingLegalPageProps) {
  const copy = pageCopy[variant]

  useEffect(() => {
    document.body.classList.add('landing-page-active')

    return () => {
      document.body.classList.remove('landing-page-active')
    }
  }, [])

  return (
    <div className="landing-page landing-legal-page">
      <header className="landing-topbar">
        <button type="button" className="landing-topbar__brand landing-topbar__brand--button" onClick={onNavigateLanding}>
          合同审查全能扫描
        </button>
        <div className="landing-topbar__actions">
          <a
            className="brutalist-button landing-button landing-button--github"
            href={GITHUB_REPOSITORY_URL}
            target="_blank"
            rel="noreferrer"
          >
            <Github size={18} strokeWidth={3} />
            GitHub
          </a>
          <button type="button" className="brutalist-button landing-button landing-button--ghost" onClick={onNavigateLogin}>
            登录
          </button>
          <button type="button" className="brutalist-button landing-button landing-button--primary" onClick={onNavigateRegister}>
            免费注册
          </button>
        </div>
      </header>

      <main className="landing-legal">
        <section className="landing-legal__panel brutalist-card">
          <div className="landing-tech__label">{copy.eyebrow}</div>
          <button type="button" className="landing-legal__back" onClick={onNavigateLanding}>
            ← 返回首页
          </button>
          <h1>{copy.title}</h1>
          <p className="landing-legal__intro">{copy.intro}</p>

          <div className="landing-legal__grid">
            {copy.sections.map((section) => (
              <article key={section.title} className="landing-legal__card">
                <h2>{section.title}</h2>
                <p>{section.body}</p>
              </article>
            ))}
          </div>

          <div className="landing-legal__contact">
            <span>还有问题？</span>
            <a href={GITHUB_ISSUES_URL} target="_blank" rel="noreferrer">
              去 GitHub Issues 联系我们
            </a>
          </div>
        </section>
      </main>
    </div>
  )
}
