import { useCallback, useEffect, useRef, useState } from 'react'
import type { RoutingDecision } from './types'
import { ChatPanel } from './components/ChatPanel'
import { DocPanel } from './components/DocPanel'
import { SideNav } from './components/SideNav'
import { useAuth } from './contexts/AuthContext'
import { useStreamingReview } from './hooks/useStreamingReview'
import { loadPersistedReviewHistory, savePersistedReviewHistory } from './lib/reviewHistory'
import { exportReportAsWord } from './lib/reportExport'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { SettingsPage } from './pages/SettingsPage'

export type ReviewStatus = 'idle' | 'uploading' | 'reviewing' | 'breakpoint' | 'complete' | 'error'
export type ModelKey = 'glm-5' | 'minimax' | 'qwen' | 'kimi' | 'gemma4'

export interface ModelOption {
  key: ModelKey
  label: string
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
  status: ReviewStatus
  filename: string
  date: string
  contractText: string
  extractedInfo: ExtractedInfo | null
  routingDecision: RoutingDecision | null
  riskCards: RiskCard[]
  finalReport: string[]
  breakpointMessage: string | null
  errorMessage: string | null
  chatMessages: ChatMessage[]
}

const DEFAULT_MODEL_KEY: ModelKey = 'gemma4'
const MODEL_STORAGE_PREFIX = 'chatModel:'
export const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  { key: 'glm-5', label: 'GLM-5' },
  { key: 'minimax', label: 'MiniMax M2.5' },
  { key: 'qwen', label: 'Qwen 3.5 Plus' },
  { key: 'kimi', label: 'Kimi K2.5' },
  { key: 'gemma4', label: 'Gemma4（本地免费）' },
]

function isModelKey(value: unknown): value is ModelKey {
  return DEFAULT_MODEL_OPTIONS.some((option) => option.key === value)
}

function getChatModelStorageKey(ownerKey?: string | null) {
  return `${MODEL_STORAGE_PREFIX}${ownerKey ?? 'anonymous'}`
}

function createSessionId() {
  return `session-${Date.now()}`
}

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

  if (phase === 'complete' || phase === 'aggregation' || phase === 'breakpoint') {
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

function hasMeaningfulChat(chatMessages: ChatMessage[]) {
  return chatMessages.some((message) => message.role === 'user') || chatMessages.length > 1
}

function shouldSaveReviewToHistory(review: ReviewState) {
  return Boolean(
    review.contractText.trim().length > 0
    || review.filename.trim().length > 0
    || review.extractedInfo
    || review.routingDecision
    || review.riskCards.length > 0
    || review.finalReport.length > 0
    || review.breakpointMessage
    || review.errorMessage
    || hasMeaningfulChat(review.chatMessages),
  )
}

function createHistoryEntry(review: ReviewState): ReviewHistoryEntry {
  return {
    sessionId: review.sessionId,
    status: review.status,
    filename: review.filename,
    date: new Date().toLocaleString('zh-CN'),
    contractText: review.contractText,
    extractedInfo: review.extractedInfo,
    routingDecision: review.routingDecision,
    riskCards: review.riskCards,
    finalReport: review.finalReport,
    breakpointMessage: review.breakpointMessage,
    errorMessage: review.errorMessage,
    chatMessages: review.chatMessages,
  }
}

function normalizeHistoryStatus(status: unknown): ReviewStatus {
  if (
    status === 'idle'
    || status === 'uploading'
    || status === 'reviewing'
    || status === 'breakpoint'
    || status === 'complete'
    || status === 'error'
  ) {
    return status
  }

  return 'complete'
}

function getRestoredHistoryStatus(entry: ReviewHistoryEntry): ReviewStatus {
  if (entry.status === 'breakpoint' && entry.breakpointMessage) {
    return 'breakpoint'
  }

  if (entry.status === 'error' && entry.errorMessage) {
    return 'error'
  }

  return 'complete'
}

function loadHistoryEntries(ownerKey?: string | null): ReviewHistoryEntry[] {
  try {
    const entries = loadPersistedReviewHistory<ReviewHistoryEntry>(ownerKey)

    return entries.map((entry) => ({
      sessionId: entry.sessionId,
      status: normalizeHistoryStatus(entry.status),
      filename: entry.filename || '未命名合同',
      date: entry.date || '',
      contractText: entry.contractText || '',
      extractedInfo: entry.extractedInfo ?? null,
      routingDecision: entry.routingDecision ?? null,
      riskCards: Array.isArray(entry.riskCards) ? entry.riskCards.map((card: any) => normalizeRiskCard(card)) : [],
      finalReport: Array.isArray(entry.finalReport) ? entry.finalReport : [],
      breakpointMessage: typeof entry.breakpointMessage === 'string' ? entry.breakpointMessage : null,
      errorMessage: typeof entry.errorMessage === 'string' ? entry.errorMessage : null,
      chatMessages: Array.isArray(entry.chatMessages) && entry.chatMessages.length > 0
        ? entry.chatMessages
        : createDefaultChatMessages(),
    }))
  } catch {
    return []
  }
}

function saveHistoryEntry(entry: ReviewHistoryEntry, ownerKey?: string | null) {
  const history = loadHistoryEntries(ownerKey).filter((item) => item.sessionId !== entry.sessionId)
  history.unshift(entry)
  if (history.length > 20) {
    history.length = 20
  }
  savePersistedReviewHistory(history, ownerKey)
}

function parseModelOptions(payload: unknown): ModelOption[] {
  if (!Array.isArray(payload)) {
    return DEFAULT_MODEL_OPTIONS
  }

  const parsed = payload
    .map((item) => {
      if (!item || typeof item !== 'object') return null
      const key = (item as { key?: unknown }).key
      const label = (item as { label?: unknown }).label
      if (!isModelKey(key) || typeof label !== 'string' || !label.trim()) {
        return null
      }
      return { key, label }
    })
    .filter((item): item is ModelOption => item !== null)

  return parsed.length > 0 ? parsed : DEFAULT_MODEL_OPTIONS
}

export default function App() {
  const { isAuthenticated, login, logout, user, token } = useAuth()
  const historyOwnerKey = user?.email?.trim().toLowerCase() ?? null
  const [authView, setAuthView] = useState<'login' | 'register'>('login')
  const [showSettings, setShowSettings] = useState(false)
  const [isExportingReport, setIsExportingReport] = useState(false)
  const [review, setReview] = useState<ReviewState>(() => createInitialState(createSessionId()))
  const [streamContractText, setStreamContractText] = useState('')
  const [availableModels, setAvailableModels] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS)
  const [selectedModel, setSelectedModel] = useState<ModelKey>(DEFAULT_MODEL_KEY)
  const previousHistoryOwnerKeyRef = useRef<string | null>(historyOwnerKey)

  const hook = useStreamingReview(review.sessionId, streamContractText, {
    enabled: review.status === 'reviewing',
    model: selectedModel,
    token,
  })

  const persistCurrentReview = useCallback((currentReview: ReviewState) => {
    if (!historyOwnerKey || !shouldSaveReviewToHistory(currentReview)) return
    saveHistoryEntry(createHistoryEntry(currentReview), historyOwnerKey)
  }, [historyOwnerKey])

  useEffect(() => {
    if (previousHistoryOwnerKeyRef.current === historyOwnerKey) {
      return
    }

    previousHistoryOwnerKeyRef.current = historyOwnerKey
    setShowSettings(false)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))

    try {
      sessionStorage.removeItem('lastReport')
    } catch {
      // Ignore storage errors.
    }
  }, [historyOwnerKey])

  useEffect(() => {
    if (!historyOwnerKey) {
      setSelectedModel(DEFAULT_MODEL_KEY)
      return
    }

    try {
      const stored = localStorage.getItem(getChatModelStorageKey(historyOwnerKey))
      setSelectedModel(isModelKey(stored) ? stored : DEFAULT_MODEL_KEY)
    } catch {
      setSelectedModel(DEFAULT_MODEL_KEY)
    }
  }, [historyOwnerKey])

  useEffect(() => {
    if (!isAuthenticated) {
      setAvailableModels(DEFAULT_MODEL_OPTIONS)
      return
    }

    let cancelled = false

    const loadModels = async () => {
      try {
        const response = await fetch('/api/models')
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const payload = await response.json() as { models?: unknown }
        if (!cancelled) {
          setAvailableModels(parseModelOptions(payload.models))
        }
      } catch {
        if (!cancelled) {
          setAvailableModels(DEFAULT_MODEL_OPTIONS)
        }
      }
    }

    void loadModels()

    return () => {
      cancelled = true
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!availableModels.some((option) => option.key === selectedModel)) {
      setSelectedModel(DEFAULT_MODEL_KEY)
    }
  }, [availableModels, selectedModel])

  useEffect(() => {
    if (!historyOwnerKey) return
    try {
      localStorage.setItem(getChatModelStorageKey(historyOwnerKey), selectedModel)
    } catch {
      // Ignore storage errors.
    }
  }, [historyOwnerKey, selectedModel])

  const handleFileUpload = useCallback((text: string, filename: string) => {
    const nextSessionId = createSessionId()
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

  const handleNewConversation = useCallback(() => {
    persistCurrentReview(review)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))
  }, [persistCurrentReview, review])

  const handleReset = useCallback(() => {
    const newSessionId = createSessionId()
    setStreamContractText('')
    setReview(createInitialState(newSessionId))
  }, [])

  const handleExportReport = useCallback(() => {
    if (review.finalReport.length === 0 || isExportingReport) return

    setIsExportingReport(true)
    exportReportAsWord({
      filename: review.filename,
      reportParagraphs: review.finalReport,
      token,
    })
      .catch(() => {
        alert('导出 Word 报告失败，请稍后重试。')
      })
      .finally(() => {
        setIsExportingReport(false)
      })
  }, [isExportingReport, review.filename, review.finalReport, token])

  const handleSendMessage = useCallback(async (message: string, model?: string) => {
    const normalizedMessage = message.trim()
    if (!normalizedMessage) return

    const activeModel = isModelKey(model) ? model : selectedModel
    const userMsgId = `user-${Date.now()}`
    const assistantMsgId = `assistant-${Date.now() + 1}`

    setReview((prev) => ({
      ...prev,
      chatMessages: [
        ...prev.chatMessages,
        { id: userMsgId, role: 'user', content: normalizedMessage },
        { id: assistantMsgId, role: 'assistant', content: '思考中...' },
      ],
    }))

    try {
      const riskSummary = review.riskCards
        .map((card) => `[${card.level}] ${card.title}：${card.issue}`)
        .join('\n')

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: normalizedMessage,
          model: activeModel,
          contract_text: review.contractText,
          risk_summary: riskSummary,
        }),
      })

      let payload: { reply?: unknown; error?: unknown; detail?: unknown } = {}
      try {
        payload = await response.json() as { reply?: unknown; error?: unknown; detail?: unknown }
      } catch {
        payload = {}
      }

      const reply = typeof payload.reply === 'string'
        ? payload.reply
        : typeof payload.error === 'string'
          ? payload.error
          : typeof payload.detail === 'string'
            ? payload.detail
            : '获取回复失败'

      setReview((prev) => ({
        ...prev,
        chatMessages: prev.chatMessages.map((chatMessage) => (
          chatMessage.id === assistantMsgId
            ? { ...chatMessage, content: reply }
            : chatMessage
        )),
      }))
    } catch {
      setReview((prev) => ({
        ...prev,
        chatMessages: prev.chatMessages.map((chatMessage) => (
          chatMessage.id === assistantMsgId
            ? { ...chatMessage, content: '网络错误，请重试。' }
            : chatMessage
        )),
      }))
    }
  }, [review.contractText, review.riskCards, selectedModel, token])

  const handleSelectHistorySession = useCallback((sessionId: string) => {
    const entry = loadHistoryEntries(historyOwnerKey).find((item) => item.sessionId === sessionId)
    if (!entry) return

    if (review.sessionId !== sessionId) {
      persistCurrentReview(review)
    }

    const restoredStatus = getRestoredHistoryStatus(entry)

    setStreamContractText('')
    setReview({
      ...createInitialState(entry.sessionId),
      status: restoredStatus,
      sessionId: entry.sessionId,
      contractText: entry.contractText,
      filename: entry.filename,
      extractedInfo: entry.extractedInfo,
      routingDecision: entry.routingDecision,
      riskCards: entry.riskCards,
      finalReport: entry.finalReport,
      breakpointMessage: restoredStatus === 'breakpoint' ? entry.breakpointMessage : null,
      errorMessage: restoredStatus === 'error' ? entry.errorMessage : null,
      chatMessages: entry.chatMessages?.length ? entry.chatMessages : createDefaultChatMessages(),
      thinkingSteps: buildThinkingSteps(restoredStatus, entry.extractedInfo, entry.routingDecision),
    })
  }, [historyOwnerKey, persistCurrentReview, review])

  useEffect(() => {
    if (!streamContractText) {
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
    if (hook.phase !== 'complete' || !review.filename || !historyOwnerKey) return
    saveHistoryEntry(createHistoryEntry(review), historyOwnerKey)
  }, [historyOwnerKey, hook.phase, review])

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
            selectedModel={selectedModel}
            availableModels={availableModels}
            onModelChange={setSelectedModel}
            onExportReport={handleExportReport}
            isExportingReport={isExportingReport}
            onBreakpointConfirm={handleBreakpointConfirm}
            onReset={handleReset}
            onSendMessage={handleSendMessage}
          />
          <DocPanel
            review={review}
            selectedModel={selectedModel}
            availableModels={availableModels}
            onModelChange={setSelectedModel}
            onFileUpload={handleFileUpload}
            onNewConversation={handleNewConversation}
          />
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
