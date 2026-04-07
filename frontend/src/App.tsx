import { useState, useCallback } from 'react'
import { ChatPanel } from './components/ChatPanel'
import { DocPanel } from './components/DocPanel'
import { TopNav } from './components/TopNav'
import { SideNav } from './components/SideNav'
import { LoginPage } from './pages/LoginPage'
import { useAuth } from './contexts/AuthContext'
import { useStreamingReview } from './hooks/useStreamingReview'

export type ReviewStatus = 'idle' | 'uploading' | 'reviewing' | 'breakpoint' | 'complete' | 'error'

export interface ReviewState {
  status: ReviewStatus
  sessionId: string
  contractText: string
  filename: string
  thinkingSteps: ThinkingStep[]
  extractedInfo: ExtractedInfo | null
  riskCards: RiskCard[]
  finalReport: string[]
  breakpointMessage: string | null
  errorMessage: string | null
}

export interface ThinkingStep {
  id: string
  label: string
  status: 'done' | 'active' | 'pending'
}

export interface ExtractedInfo {
  lessor: string
  lessee: string
  property: string
  monthlyRent: number
  deposit: number
  leaseTerm: string
}

export interface RiskCard {
  id: string
  level: 'high' | 'medium'
  title: string
  clause: string
  issue: string
  suggestion: string
  legalRef: string
}

function createInitialState(sessionId: string): ReviewState {
  return {
    status: 'idle',
    sessionId,
    contractText: '',
    filename: '',
    thinkingSteps: [
      { id: 'parse', label: '解析合同主体信息', status: 'pending' },
      { id: 'extract', label: '提取关键条款变量', status: 'pending' },
      { id: 'retrieve', label: '检索相关法律依据', status: 'pending' },
      { id: 'review', label: '扫描风险项', status: 'pending' },
    ],
    extractedInfo: null,
    riskCards: [],
    finalReport: [],
    breakpointMessage: null,
    errorMessage: null,
  }
}

function mapPhaseToStatus(phase: string): ReviewStatus {
  switch (phase) {
    case 'idle': return 'idle'
    case 'started': return 'reviewing'
    case 'extraction': return 'reviewing'
    case 'routing': return 'reviewing'
    case 'logic_review': return 'reviewing'
    case 'breakpoint': return 'breakpoint'
    case 'aggregation': return 'reviewing'
    case 'complete': return 'complete'
    case 'error': return 'error'
    default: return 'idle'
  }
}

function mapEntities(extracted: any): ExtractedInfo | null {
  if (!extracted) return null
  return {
    lessor: extracted.parties?.lessor || extracted.lessor || '未知',
    lessee: extracted.parties?.lessee || extracted.lessee || '未知',
    property: extracted.property?.address || extracted.property || '未知',
    monthlyRent: extracted.rent?.monthly || extracted.monthlyRent || 0,
    deposit: extracted.deposit?.amount || extracted.deposit || 0,
    leaseTerm: extracted.lease_term?.duration_text || extracted.leaseTerm || '未知',
  }
}

function mapIssues(issues: any[]): RiskCard[] {
  return issues.map((issue, idx) => ({
    id: String(idx + 1),
    level: issue.level === 'critical' || issue.level === 'high' ? 'high' : 'medium',
    title: issue.clause || `风险项${idx + 1}`,
    clause: issue.clause || '',
    issue: issue.issue || '',
    suggestion: issue.suggestion || '',
    legalRef: issue.legal_reference || issue.legalRef || '',
  }))
}

function buildThinkingSteps(phase: string, extracted: any, routing: any) {
  type StepStatus = 'done' | 'active' | 'pending'

  const statuses: Record<string, StepStatus> = {
    parse: 'pending',
    extract: 'pending',
    retrieve: 'pending',
    review: 'pending',
  }

  if (phase === 'idle') {
    // all pending
  } else if (extracted) {
    statuses.parse = 'done'
    statuses.extract = 'done'
  }

  if (routing) {
    statuses.retrieve = 'done'
  }

  if (phase === 'aggregation' || phase === 'complete') {
    statuses.review = 'done'
  } else if (phase === 'started' || phase === 'extraction') {
    statuses.extract = 'active'
  } else if (phase === 'routing') {
    statuses.retrieve = 'active'
  } else if (phase === 'logic_review') {
    statuses.review = 'active'
  }

  return [
    { id: 'parse', label: '解析合同主体信息', status: statuses.parse },
    { id: 'extract', label: '提取关键条款变量', status: statuses.extract },
    { id: 'retrieve', label: '检索相关法律依据', status: statuses.retrieve },
    { id: 'review', label: '扫描风险项', status: statuses.review },
  ]
}

export default function App() {
  const { isAuthenticated, login, logout } = useAuth()
  const [review, setReview] = useState<ReviewState>({
    ...createInitialState(`session-${Date.now()}`),
  })
  const [contractText, setContractText] = useState('')

  const hook = useStreamingReview(review.sessionId, contractText)

  const handleFileUpload = useCallback((text: string, filename: string) => {
    setContractText(text)
    setReview(prev => ({
      ...prev,
      status: 'reviewing',
      contractText: text,
      filename,
    }))
  }, [])

  const handleBreakpointConfirm = useCallback(() => {
    hook.confirm()
  }, [hook.confirm])

  const handleReset = useCallback(() => {
    const newSessionId = `session-${Date.now()}`
    setReview(createInitialState(newSessionId))
    setContractText('')
  }, [])

  const handleSendMessage = useCallback((message: string) => {
    console.log('User message:', message)
  }, [])

  // Show login if not authenticated
  if (!isAuthenticated) {
    return <LoginPage onLogin={login} />
  }

  const appStatus = mapPhaseToStatus(hook.phase)
  const extractedInfo = mapEntities(hook.extractedEntities)
  const riskCards = mapIssues(hook.issues)
  const thinkingSteps = buildThinkingSteps(hook.phase, hook.extractedEntities, hook.routingDecision)
  const breakpointMessage = hook.breakpointData
    ? `已检测到 ${hook.issues.length} 处风险条款，请确认是否继续生成完整的避坑指南报告？`
    : null

  return (
    <div className="app-layout">
      <TopNav user={useAuth().user} onLogout={logout} />
      <SideNav activeItem="chat" />
      <main className="workspace">
        <ChatPanel
          review={{
            status: hook.error ? 'error' : appStatus,
            sessionId: review.sessionId,
            contractText,
            filename: review.filename,
            thinkingSteps,
            extractedInfo,
            riskCards,
            finalReport: hook.reportParagraphs,
            breakpointMessage: hook.error ? hook.error : breakpointMessage,
            errorMessage: hook.error || null,
          }}
          onBreakpointConfirm={handleBreakpointConfirm}
          onReset={handleReset}
          onSendMessage={handleSendMessage}
        />
        <DocPanel
          review={{
            status: hook.error ? 'error' : appStatus,
            sessionId: review.sessionId,
            contractText,
            filename: review.filename,
            thinkingSteps,
            extractedInfo,
            riskCards,
            finalReport: hook.reportParagraphs,
            breakpointMessage: hook.error ? hook.error : breakpointMessage,
            errorMessage: hook.error || null,
          }}
          onFileUpload={handleFileUpload}
        />
      </main>
      {appStatus === 'reviewing' && (
        <button className="fab" onClick={handleReset}>
          <span className="material-symbols-outlined fab__icon">refresh</span>
          <span>深度扫描</span>
        </button>
      )}
    </div>
  )
}

