import { useCallback, useEffect, useState } from 'react'
import type { RoutingDecision } from './types'
import { ChatPanel } from './components/ChatPanel'
import { DocPanel } from './components/DocPanel'
import { SideNav } from './components/SideNav'
import { useAuth } from './contexts/AuthContext'
import { useStreamingReview } from './hooks/useStreamingReview'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { SettingsPage } from './pages/SettingsPage'

export type ReviewStatus = 'idle' | 'uploading' | 'reviewing' | 'breakpoint' | 'complete' | 'error'

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
  matchedText: string
}

export interface ChatMessage {
  id: string
  role: 'assistant' | 'user'
  content: string
}

export interface ReviewState {
  status: ReviewStatus
  sessionId: string
  contractText: string
  filename: string
  thinkingSteps: ThinkingStep[]
  extractedInfo: ExtractedInfo | null
  routingDecision: RoutingDecision | null
  riskCards: RiskCard[]
  finalReport: string[]
  breakpointMessage: string | null
  errorMessage: string | null
  chatMessages: ChatMessage[]
}

export interface ReviewHistoryEntry {
  sessionId: string
  filename: string
  date: string
  contractText: string
  extractedInfo: ExtractedInfo | null
  routingDecision: RoutingDecision | null
  riskCards: RiskCard[]
  finalReport: string[]
  chatMessages: ChatMessage[]
}

const HISTORY_STORAGE_KEY = 'reviewHistory'

function createDefaultChatMessages(): ChatMessage[] {
  return [
    {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '上传合同后，我可以帮你概括风险、解释条款，并给出重点修改建议。',
    },
  ]
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
    routingDecision: null,
    riskCards: [],
    finalReport: [],
    breakpointMessage: null,
    errorMessage: null,
    chatMessages: createDefaultChatMessages(),
  }
}

function mapPhaseToStatus(phase: string): ReviewStatus {
  switch (phase) {
    case 'idle':
      return 'idle'
    case 'started':
    case 'extraction':
    case 'routing':
    case 'logic_review':
    case 'aggregation':
      return 'reviewing'
    case 'breakpoint':
      return 'breakpoint'
    case 'complete':
      return 'complete'
    case 'error':
      return 'error'
    default:
      return 'idle'
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
    matchedText: issue.matched_text || issue.matchedText || '',
  }))
}

function normalizeRiskCard(card: any): RiskCard {
  return {
    id: String(card.id ?? Date.now()),
    level: card.level === 'high' ? 'high' : 'medium',
    title: card.title || card.clause || '风险项',
    clause: card.clause || '',
    issue: card.issue || '',
    suggestion: card.suggestion || '',
    legalRef: card.legalRef || card.legal_reference || '',
    matchedText: card.matchedText || card.matched_text || '',
  }
}

function buildThinkingSteps(phase: string, extracted: ExtractedInfo | null, routing: RoutingDecision | null) {
  type StepStatus = 'done' | 'active' | 'pending'

  const statuses: Record<string, StepStatus> = {
    parse: 'pending',
    extract: 'pending',
    retrieve: 'pending',
    review: 'pending',
  }

  if (extracted) {
    statuses.parse = 'done'
    statuses.extract = 'done'
  }

  if (routing) {
    statuses.retrieve = 'done'
  }

  if (phase === 'complete' || phase === 'aggregation') {
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

function summarizeRisks(riskCards: RiskCard[]) {
  if (riskCards.length === 0) {
    return '当前没有识别到明显高风险条款。'
  }

  const highRiskCount = riskCards.filter((card) => card.level === 'high').length
  const lead = riskCards[0]
  return `本次审查共识别 ${riskCards.length} 条风险，其中 ${highRiskCount} 条为高风险，最先需要处理的是“${lead.title}”。`
}

function findRiskByKeyword(riskCards: RiskCard[], keyword: string) {
  return riskCards.find((card) =>
    [card.title, card.clause, card.issue, card.suggestion].some((value) => value.includes(keyword)),
  )
}

function buildAssistantReply(message: string, review: ReviewState) {
  const normalized = message.trim().toLowerCase()

  if (!review.contractText) {
    return '先上传一份合同文本，我就可以结合条款内容给你总结风险和修改建议。'
  }

  if (review.status === 'reviewing') {
    return '合同还在审查中，我已经开始提取关键信息。等流式结果出来后，我可以给你更准确的结论。'
  }

  if (normalized.includes('总结') || normalized.includes('概括') || normalized.includes('结论')) {
    return `${summarizeRisks(review.riskCards)}${review.finalReport[0] ? ` 报告开头是：${review.finalReport[0]}` : ''}`
  }

  if (normalized.includes('押金')) {
    const match = findRiskByKeyword(review.riskCards, '押金')
    return match
      ? `押金相关风险在“${match.title}”。问题是：${match.issue}。建议优先按这条修改：${match.suggestion}`
      : `当前提取到的押金金额是 ${review.extractedInfo?.deposit ?? 0} 元，暂时没有单独命中的押金风险卡。`
  }

  if (normalized.includes('违约金') || normalized.includes('解约')) {
    const match = findRiskByKeyword(review.riskCards, '违约')
      ?? findRiskByKeyword(review.riskCards, '解约')
    return match
      ? `违约责任里最值得关注的是“${match.title}”。核心问题：${match.issue}。建议：${match.suggestion}`
      : '我还没有匹配到明确的违约金风险卡，可以结合最终报告再核对一次相关条款。'
  }

  if (normalized.includes('怎么改') || normalized.includes('修改') || normalized.includes('建议')) {
    if (review.riskCards.length === 0) {
      return '目前没有识别到需要优先修改的条款。如果你愿意，我可以继续根据最终报告帮你逐条解释。'
    }

    return review.riskCards
      .slice(0, 3)
      .map((card, index) => `${index + 1}. ${card.title}：${card.suggestion}`)
      .join('\n')
  }

  if (normalized.includes('谁') || normalized.includes('甲方') || normalized.includes('乙方')) {
    return `当前识别到的合同主体是：甲方/出租方“${review.extractedInfo?.lessor ?? '未知'}”，乙方/承租方“${review.extractedInfo?.lessee ?? '未知'}”。`
  }

  if (normalized.includes('导出') || normalized.includes('报告')) {
    return review.finalReport.length > 0
      ? '报告已经生成完成，可以直接点击顶部“导出报告”下载当前避坑指南。'
      : '完整报告还没有生成完。等审查完成后，我会提示你导出。'
  }

  return '我可以继续帮你做三件事：概括风险结论、解释某一条风险卡、或者把修改建议整理成可执行清单。你也可以直接问我“押金风险在哪”或“这份合同怎么改”。'
}

function loadHistoryEntries(): ReviewHistoryEntry[] {
  try {
    const entries = JSON.parse(sessionStorage.getItem(HISTORY_STORAGE_KEY) || '[]')
    if (!Array.isArray(entries)) return []

    return entries.map((entry) => ({
      sessionId: entry.sessionId,
      filename: entry.filename || '未命名合同',
      date: entry.date || '',
      contractText: entry.contractText || '',
      extractedInfo: entry.extractedInfo ?? null,
      routingDecision: entry.routingDecision ?? null,
      riskCards: Array.isArray(entry.riskCards) ? entry.riskCards.map((card: any) => normalizeRiskCard(card)) : [],
      finalReport: Array.isArray(entry.finalReport) ? entry.finalReport : [],
      chatMessages: Array.isArray(entry.chatMessages) && entry.chatMessages.length > 0
        ? entry.chatMessages
        : createDefaultChatMessages(),
    }))
  } catch {
    return []
  }
}

function saveHistoryEntry(entry: ReviewHistoryEntry) {
  const history = loadHistoryEntries().filter((item) => item.sessionId !== entry.sessionId)
  history.unshift(entry)
  if (history.length > 20) {
    history.length = 20
  }
  sessionStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history))
}

export default function App() {
  const { isAuthenticated, login, logout, user, token } = useAuth()
  const [authView, setAuthView] = useState<'login' | 'register'>('login')
  const [showSettings, setShowSettings] = useState(false)
  const [review, setReview] = useState<ReviewState>(() => createInitialState(`session-${Date.now()}`))
  const [streamContractText, setStreamContractText] = useState('')

  const hook = useStreamingReview(review.sessionId, streamContractText, {
    enabled: review.status === 'reviewing',
    token,
  })

  const handleFileUpload = useCallback((text: string, filename: string) => {
    const nextSessionId = `session-${Date.now()}`
    setStreamContractText(text)
    setReview({
      ...createInitialState(nextSessionId),
      status: 'reviewing',
      sessionId: nextSessionId,
      contractText: text,
      filename,
    })
  }, [])

  const handleBreakpointConfirm = useCallback(() => {
    hook.confirm()
  }, [hook])

  const handleReset = useCallback(() => {
    const newSessionId = `session-${Date.now()}`
    setStreamContractText('')
    setReview(createInitialState(newSessionId))
  }, [])

  const handleExportReport = useCallback(() => {
    if (review.finalReport.length === 0) return

    const reportText = review.finalReport.join('\n\n')
    sessionStorage.setItem('lastReport', reportText)

    const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `避坑指南_${new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }, [review.finalReport])

  const handleSendMessage = useCallback((message: string) => {
    setReview((prev) => {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: message,
      }
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now() + 1}`,
        role: 'assistant',
        content: buildAssistantReply(message, prev),
      }
      return {
        ...prev,
        chatMessages: [...prev.chatMessages, userMessage, assistantMessage],
      }
    })
  }, [])

  const handleSelectHistorySession = useCallback((sessionId: string) => {
    const entry = loadHistoryEntries().find((item) => item.sessionId === sessionId)
    if (!entry) return

    setStreamContractText('')
    setReview({
      ...createInitialState(entry.sessionId),
      status: 'complete',
      sessionId: entry.sessionId,
      contractText: entry.contractText,
      filename: entry.filename,
      extractedInfo: entry.extractedInfo,
      routingDecision: entry.routingDecision,
      riskCards: entry.riskCards,
      finalReport: entry.finalReport,
      chatMessages: entry.chatMessages?.length ? entry.chatMessages : createDefaultChatMessages(),
      thinkingSteps: buildThinkingSteps('complete', entry.extractedInfo, entry.routingDecision),
    })
  }, [])

  useEffect(() => {
    if (!streamContractText && hook.phase === 'idle' && !hook.error) {
      return
    }

    setReview((prev) => {
      const nextExtractedInfo = mapEntities(hook.extractedEntities) ?? prev.extractedInfo
      const nextRoutingDecision = hook.routingDecision ?? prev.routingDecision
      const nextRiskCards = hook.issues.length > 0 ? mapIssues(hook.issues) : prev.riskCards
      const nextFinalReport = hook.reportParagraphs.length > 0 ? hook.reportParagraphs : prev.finalReport
      const nextStatus = hook.error
        ? 'error'
        : hook.phase === 'idle'
          ? prev.status
          : mapPhaseToStatus(hook.phase)
      const nextBreakpointMessage = hook.phase === 'breakpoint' && hook.breakpointData
        ? `已检测到 ${hook.issues.length} 处风险条款，请确认是否继续生成完整的避坑指南报告？`
        : null

      return {
        ...prev,
        status: nextStatus,
        extractedInfo: nextExtractedInfo,
        routingDecision: nextRoutingDecision,
        riskCards: nextRiskCards,
        finalReport: nextFinalReport,
        breakpointMessage: hook.error ? hook.error : nextBreakpointMessage,
        errorMessage: hook.error || null,
        thinkingSteps: buildThinkingSteps(hook.phase, nextExtractedInfo, nextRoutingDecision),
      }
    })
  }, [
    hook.breakpointData,
    hook.error,
    hook.extractedEntities,
    hook.issues,
    hook.phase,
    hook.reportParagraphs,
    hook.routingDecision,
    streamContractText,
  ])

  useEffect(() => {
    if (hook.phase !== 'complete' || !review.filename) return

    saveHistoryEntry({
      sessionId: review.sessionId,
      filename: review.filename,
      date: new Date().toLocaleString('zh-CN'),
      contractText: review.contractText,
      extractedInfo: review.extractedInfo,
      routingDecision: review.routingDecision,
      riskCards: review.riskCards,
      finalReport: review.finalReport,
      chatMessages: review.chatMessages,
    })
  }, [hook.phase, review])

  if (!isAuthenticated) {
    if (authView === 'register') {
      return <RegisterPage onNavigateLogin={() => setAuthView('login')} />
    }
    return <LoginPage onLogin={login} onNavigateRegister={() => setAuthView('register')} />
  }

  if (showSettings) {
    return <SettingsPage user={user} onBack={() => setShowSettings(false)} />
  }

  return (
    <div className="app-layout" style={{ flexDirection: 'row' }}>
      <SideNav
        user={user}
        onLogout={logout}
        onSelectHistorySession={handleSelectHistorySession}
        onOpenSettings={() => setShowSettings(true)}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <main className="workspace">
          <ChatPanel
            review={review}
            authToken={token}
            onBreakpointConfirm={handleBreakpointConfirm}
            onReset={handleReset}
            onSendMessage={handleSendMessage}
          />
          <DocPanel review={review} onFileUpload={handleFileUpload} onExportReport={handleExportReport} />
        </main>
      </div>
      {review.status === 'reviewing' && (
        <button className="fab" onClick={handleReset}>
          ↺ 重新扫描
        </button>
      )}
    </div>
  )
}
