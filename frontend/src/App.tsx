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
const GEMMA4_MODEL_LABEL = 'Gemma4（免费模型）'

export const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  { key: 'gemma4', label: GEMMA4_MODEL_LABEL },
  { key: 'glm-5', label: 'GLM-5' },
  { key: 'minimax', label: 'MiniMax M2.5' },
  { key: 'qwen', label: 'Qwen 3.5 Plus' },
  { key: 'kimi', label: 'Kimi K2.5' },
]

function isModelKey(value: unknown): value is ModelKey {
  return DEFAULT_MODEL_OPTIONS.some((option) => option.key === value)
}

function getChatModelStorageKey(ownerKey?: string | null) {
  return `${MODEL_STORAGE_PREFIX}${ownerKey ?? 'anonymous'}`
}

function getModelLabel(modelKey: ModelKey) {
  return DEFAULT_MODEL_OPTIONS.find((option) => option.key === modelKey)?.label ?? modelKey
}

function normalizeModelOptions(models: unknown): ModelOption[] {
  if (!Array.isArray(models)) {
    return DEFAULT_MODEL_OPTIONS
  }

  const normalized: ModelOption[] = []
  const seen = new Set<ModelKey>()

  for (const model of models) {
    if (!model || typeof model !== 'object') continue

    const maybeKey = (model as { key?: unknown }).key
    if (!isModelKey(maybeKey) || seen.has(maybeKey)) continue

    const maybeLabel = (model as { label?: unknown }).label
    normalized.push({
      key: maybeKey,
      label: typeof maybeLabel === 'string' && maybeLabel.trim()
        ? maybeLabel
        : getModelLabel(maybeKey),
    })
    seen.add(maybeKey)
  }

  return normalized.length > 0 ? normalized : DEFAULT_MODEL_OPTIONS
}

function loadStoredModel(ownerKey?: string | null): ModelKey | null {
  try {
    const storedModel = localStorage.getItem(getChatModelStorageKey(ownerKey))
    return isModelKey(storedModel) ? storedModel : null
  } catch {
    return null
  }
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
      { id: 'review', label: '扫描风险项目', status: 'pending' },
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
    lessor: extracted.parties?.lessor || extracted.lessor || '鏈煡',
    lessee: extracted.parties?.lessee || extracted.lessee || '鏈煡',
    property: extracted.property?.address || extracted.property || '鏈煡',
    monthlyRent: extracted.rent?.monthly || extracted.monthlyRent || 0,
    deposit: extracted.deposit?.amount || extracted.deposit || 0,
    leaseTerm: extracted.lease_term?.duration_text || extracted.leaseTerm || '鏈煡',
  }
}

function mapIssues(issues: any[]): RiskCard[] {
  return issues.map((issue, index) => ({
    id: String(index + 1),
    level: issue.level === 'critical' || issue.level === 'high' ? 'high' : 'medium',
    title: issue.clause || `风险项 ${index + 1}`,
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

export function buildThinkingSteps(
  phase: string,
  extracted: ExtractedInfo | null,
  routing: RoutingDecision | null,
) {
  type StepStatus = 'done' | 'active' | 'pending'

  const statuses: Record<string, StepStatus> = {
    parse: 'pending',
    extract: 'pending',
    retrieve: 'pending',
    review: 'pending',
  }

  if (phase === 'started') {
    statuses.parse = 'active'
  } else if (phase === 'extraction') {
    statuses.parse = 'done'
    statuses.extract = 'active'
  } else if (phase === 'routing') {
    statuses.parse = 'done'
    statuses.extract = 'done'
    statuses.retrieve = 'active'
  } else if (phase === 'logic_review') {
    statuses.parse = 'done'
    statuses.extract = 'done'
    statuses.retrieve = 'done'
    statuses.review = 'active'
  } else if (phase === 'aggregation' || phase === 'breakpoint' || phase === 'complete') {
    statuses.parse = 'done'
    statuses.extract = 'done'
    statuses.retrieve = 'done'
    statuses.review = 'done'
  } else {
    if (extracted) {
      statuses.parse = 'done'
      statuses.extract = 'done'
    }
    if (routing) {
      statuses.retrieve = 'done'
    }
  }

  return [
    { id: 'parse', label: '解析合同主体信息', status: statuses.parse },
    { id: 'extract', label: '提取关键条款变量', status: statuses.extract },
    { id: 'retrieve', label: '检索相关法律依据', status: statuses.retrieve },
    { id: 'review', label: '扫描风险项目', status: statuses.review },
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
    || hasMeaningfulChat(review.chatMessages)
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
      riskCards: Array.isArray(entry.riskCards)
        ? entry.riskCards.map((card: any) => normalizeRiskCard(card))
        : [],
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

export default function App() {
  const { isAuthenticated, login, logout, user, token } = useAuth()
  const historyOwnerKey = user?.email?.trim().toLowerCase() ?? null
  const [authView, setAuthView] = useState<'login' | 'register'>('login')
  const [showSettings, setShowSettings] = useState(false)
  const [isExportingReport, setIsExportingReport] = useState(false)
  const [availableModels, setAvailableModels] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS)
  const [selectedModel, setSelectedModel] = useState<ModelKey>(() => (
    loadStoredModel(historyOwnerKey) ?? DEFAULT_MODEL_KEY
  ))
  const [review, setReview] = useState<ReviewState>(() => createInitialState(createSessionId()))
  const [streamContractText, setStreamContractText] = useState('')
  const previousHistoryOwnerKeyRef = useRef<string | null>(historyOwnerKey)
  const prevPhaseRef = useRef<ReviewStatus>(review.status)
  const reviewRef = useRef(review)

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
    reviewRef.current = review
  }, [review])

  useEffect(() => {
    if (previousHistoryOwnerKeyRef.current === historyOwnerKey) {
      return
    }

    previousHistoryOwnerKeyRef.current = historyOwnerKey
    setShowSettings(false)
    setSelectedModel(loadStoredModel(historyOwnerKey) ?? DEFAULT_MODEL_KEY)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))

    try {
      sessionStorage.removeItem('lastReport')
    } catch {
      // Ignore storage errors.
    }
  }, [historyOwnerKey])

  useEffect(() => {
    let isCancelled = false
    const abortController = new AbortController()

    async function syncModels() {
      try {
        const response = await fetch('/api/models', {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: abortController.signal,
        })

        if (!response.ok) {
          throw new Error(`Failed to load models: ${response.status}`)
        }

        const payload = await response.json() as { default_model?: unknown; models?: unknown }
        if (isCancelled) return

        const nextOptions = normalizeModelOptions(payload.models)
        const serverDefault = isModelKey(payload.default_model) ? payload.default_model : DEFAULT_MODEL_KEY
        const storedModel = loadStoredModel(historyOwnerKey)
        const fallbackModel = nextOptions.some((option) => option.key === serverDefault)
          ? serverDefault
          : nextOptions[0]?.key ?? DEFAULT_MODEL_KEY

        setAvailableModels(nextOptions)
        setSelectedModel((current) => (
          nextOptions.some((option) => option.key === current)
            ? current
            : storedModel && nextOptions.some((option) => option.key === storedModel)
              ? storedModel
              : fallbackModel
        ))
      } catch (error) {
        if (abortController.signal.aborted || isCancelled) return

        setAvailableModels(DEFAULT_MODEL_OPTIONS)
        setSelectedModel((current) => (
          DEFAULT_MODEL_OPTIONS.some((option) => option.key === current)
            ? current
            : loadStoredModel(historyOwnerKey) ?? DEFAULT_MODEL_KEY
        ))
      }
    }

    void syncModels()

    return () => {
      isCancelled = true
      abortController.abort()
    }
  }, [historyOwnerKey, token])

  useEffect(() => {
    try {
      localStorage.setItem(getChatModelStorageKey(historyOwnerKey), selectedModel)
    } catch {
      // Ignore storage errors in tests or private browsing.
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

  const handleSendMessage = useCallback(async (message: string) => {
    const normalizedMessage = message.trim()
    if (!normalizedMessage) return

    const userMsgId = `user-${Date.now()}`
    const assistantMsgId = `assistant-${Date.now() + 1}`

    setReview((prev) => ({
      ...prev,
      chatMessages: [
        ...prev.chatMessages,
        { id: userMsgId, role: 'user', content: normalizedMessage },
        { id: assistantMsgId, role: 'assistant', content: '鎬濊€冧腑...' },
      ],
    }))

    try {
      const riskSummary = review.riskCards
        .map((card) => `[${card.level}] ${card.title}: ${card.issue}`)
        .join('\n')

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: normalizedMessage,
          model: selectedModel,
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
            : '鑾峰彇鍥炲澶辫触'

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
    const prevPhase = prevPhaseRef.current
    if (review.status === 'complete' && prevPhase !== 'complete' && review.filename && historyOwnerKey) {
      saveHistoryEntry(createHistoryEntry(reviewRef.current), historyOwnerKey)
    }
    prevPhaseRef.current = review.status
  }, [historyOwnerKey, review.filename, review.status])

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
          閲嶆柊鎵弿
        </button>
      )}
    </div>
  )
}



