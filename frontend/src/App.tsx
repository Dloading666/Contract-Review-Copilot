import { useCallback, useEffect, useRef, useState } from 'react'
import type { ClauseIssue, RoutingDecision } from './types'
import { ChatPanel } from './components/ChatPanel'
import { DisclaimerModal } from './components/DisclaimerModal'
import { DocPanel } from './components/DocPanel'
import { SideNav } from './components/SideNav'
import { useAuth } from './contexts/AuthContext'
import { loadDisclaimerAcceptance, persistDisclaimerAcceptance } from './lib/disclaimer'
import { useStreamingReview } from './hooks/useStreamingReview'
import { loadPersistedReviewHistoryFromOwners, savePersistedReviewHistory } from './lib/reviewHistory'
import { exportReportAsWord } from './lib/reportExport'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { RegisterPage } from './pages/RegisterPage'
import { SettingsPage } from './pages/SettingsPage'
import { safeFetchJSON } from './lib/apiClient'
import { apiPath } from './lib/apiPaths'
import { createSSEClient } from './lib/sseClient'

export type ReviewStatus = 'idle' | 'uploading' | 'ocr_ready' | 'reviewing' | 'breakpoint' | 'complete' | 'error'
export type ReviewDocumentSource = 'direct' | 'ocr'

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
  changeType?: 'new' | 'upgraded' | 'none'
}

export interface ChatMessage {
  status?: 'retrieving' | 'streaming' | 'complete' | 'error'
  id: string
  role: 'assistant' | 'user'
  content: string
}

export interface ReviewState {
  status: ReviewStatus
  reviewStage: 'idle' | 'initial' | 'deep' | 'complete'
  sessionId: string
  documentSource?: ReviewDocumentSource
  contractText: string
  filename: string
  ocrWarnings?: string[]
  thinkingSteps: ThinkingStep[]
  extractedInfo: ExtractedInfo | null
  routingDecision: RoutingDecision | null
  riskCards: RiskCard[]
  finalReport: string[]
  initialSummary: string | null
  deepUpdateNotice: string | null
  breakpointMessage: string | null
  errorMessage: string | null
  chatMessages: ChatMessage[]
}

export interface ReviewHistoryEntry {
  sessionId: string
  status: ReviewStatus
  reviewStage: 'idle' | 'initial' | 'deep' | 'complete'
  documentSource?: ReviewDocumentSource
  filename: string
  date: string
  contractText: string
  ocrWarnings?: string[]
  extractedInfo: ExtractedInfo | null
  routingDecision: RoutingDecision | null
  riskCards: RiskCard[]
  finalReport: string[]
  initialSummary: string | null
  deepUpdateNotice: string | null
  breakpointMessage: string | null
  errorMessage: string | null
  chatMessages: ChatMessage[]
}

interface PendingReviewStart {
  text: string
  filename: string
}

function createSessionId() {
  return `session-${Date.now()}`
}

function inferDocumentSource(value: {
  documentSource?: unknown
  filename?: unknown
  ocrWarnings?: unknown
}): ReviewDocumentSource {
  if (value.documentSource === 'ocr' || value.documentSource === 'direct') {
    return value.documentSource
  }

  const filename = typeof value.filename === 'string' ? value.filename.toLowerCase() : ''
  if (
    filename.endsWith('.pdf')
    || filename.endsWith('.png')
    || filename.endsWith('.jpg')
    || filename.endsWith('.jpeg')
    || filename.endsWith('.webp')
    || filename.includes('图片')
    || filename.includes('照片')
  ) {
    return 'ocr'
  }

  const warnings = Array.isArray(value.ocrWarnings) ? value.ocrWarnings : []
  return warnings.length > 0 ? 'ocr' : 'direct'
}

function createDefaultChatMessages(): ChatMessage[] {
  return [
    {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      status: 'complete',
      content: '上传合同后，我可以帮你概括风险、解释条款，并给出重点修改建议。',
    },
  ]
}

function normalizeChatMessage(message: any): ChatMessage {
  const role = message?.role === 'user' ? 'user' : 'assistant'
  const status = ['retrieving', 'streaming', 'complete', 'error'].includes(message?.status)
    ? message.status
    : 'complete'
  return {
    id: String(message?.id ?? `${role}-${Date.now()}`),
    role,
    content: typeof message?.content === 'string' ? message.content : '',
    status,
  }
}

function getStreamText(data: unknown, key: string) {
  if (!data || typeof data !== 'object') return ''
  const value = (data as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : ''
}

function createInitialState(sessionId: string): ReviewState {
  return {
    status: 'idle',
    reviewStage: 'idle',
    sessionId,
    documentSource: 'direct',
    contractText: '',
    filename: '',
    ocrWarnings: [],
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
    initialSummary: null,
    deepUpdateNotice: null,
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
    case 'initial_ready':
    case 'deep_review':
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
  return issues.map((issue, index) => ({
    id: `${issue.clause || 'risk'}-${issue.issue || index}`,
    level: issue.level === 'critical' || issue.level === 'high' ? 'high' : 'medium',
    title: issue.clause || `风险项 ${index + 1}`,
    clause: issue.clause || '',
    issue: issue.issue || '',
    suggestion: issue.suggestion || '',
    legalRef: issue.legal_reference || issue.legalRef || '',
    matchedText: issue.matched_text || issue.matchedText || '',
    changeType: issue.change_type === 'new' || issue.change_type === 'upgraded' ? issue.change_type : 'none',
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
    changeType: card.changeType === 'new' || card.changeType === 'upgraded' ? card.changeType : 'none',
  }
}

function mapRiskCardsToIssuePayload(riskCards: RiskCard[]): ClauseIssue[] {
  return riskCards.map((card) => ({
    clause: card.clause || card.title,
    issue: card.issue,
    level: card.level === 'high' ? 'high' : 'medium',
    severity: card.level === 'high' ? 'high' : 'medium',
    risk_level: card.level === 'high' ? 4 : 2,
    suggestion: card.suggestion,
    legal_reference: card.legalRef,
    matched_text: card.matchedText,
    change_type: card.changeType ?? 'none',
  }))
}

function isNoRiskExportCard(card: RiskCard) {
  const summaryText = `${card.title} ${card.clause}`.toLowerCase()
  const issueText = `${card.issue} ${card.suggestion}`
  return (
    (summaryText.includes('整体评估') || summaryText.includes('风险评估'))
    && (
      issueText.includes('未发现明显不公平条款')
      || issueText.includes('合同条款基本公平合理')
      || issueText.includes('未发现明显不公平')
    )
  )
}

function formatRiskLevelLabel(level: RiskCard['level']) {
  return level === 'high' ? '高风险' : '提示'
}

export function buildReportExportParagraphs(review: ReviewState): string[] {
  const finalReport = review.finalReport.filter((paragraph) => paragraph.trim())
  if (finalReport.length > 0) return finalReport

  const hasUnifiedScanResult = Boolean(
    review.initialSummary
    || review.deepUpdateNotice
    || review.riskCards.length > 0
  )
  if (!hasUnifiedScanResult) return []

  const riskCards = review.riskCards.filter((card) => !isNoRiskExportCard(card))
  const noRiskCard = review.riskCards.find((card) => isNoRiskExportCard(card))
  const generatedAt = new Date().toLocaleString('zh-CN')
  const sourceName = review.filename || '未命名合同'
  const summary = review.initialSummary || review.deepUpdateNotice || (
    riskCards.length > 0
      ? `合同分析已完成，识别到 ${riskCards.length} 处潜在风险。`
      : '合同分析已完成，当前未发现明显不公平条款。'
  )

  const paragraphs = [
    `## 合同审查报告\n\n来源文件：${sourceName}\n\n生成时间：${generatedAt}`,
    `### 分析结论\n\n${summary}`,
  ]

  if (riskCards.length > 0) {
    paragraphs.push(`### 风险条款摘要\n\n共识别 ${riskCards.length} 处潜在风险。`)
    riskCards.forEach((card, index) => {
      paragraphs.push(
        `### 风险项目 ${index + 1}：${card.title || card.clause || '风险项'}\n\n`
        + `风险等级：${formatRiskLevelLabel(card.level)}\n\n`
        + `相关条款：${card.clause || '未明确'}\n\n`
        + `问题分析：${card.issue || '未明确'}\n\n`
        + `处置建议：${card.suggestion || '建议签约前进一步核对并协商明确。'}\n\n`
        + `参考依据：${card.legalRef || '《民法典》合同编及相关租赁合同规则'}`,
      )
    })
  } else {
    paragraphs.push(
      `### 风险条款摘要\n\n${noRiskCard?.issue || '当前未发现明显不公平条款。'}\n\n`
      + `建议：${noRiskCard?.suggestion || '签约前仍建议逐条核对押金、维修、解约、违约责任和证据留存要求。'}`,
    )
  }

  paragraphs.push(
    '### 后续建议\n\n本报告用于快速定位主要风险。签约前建议继续核对押金、解约、维修、违约责任和证据留存要求，并按需补充人工复核。',
  )

  return paragraphs
}

export function canExportReviewReport(review: ReviewState) {
  if (review.finalReport.some((paragraph) => paragraph.trim())) return true
  if (review.status !== 'complete') return false
  return buildReportExportParagraphs(review).length > 0
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
    || review.initialSummary
    || review.deepUpdateNotice
    || review.breakpointMessage
    || review.errorMessage
    || hasMeaningfulChat(review.chatMessages)
  )
}

function createHistoryEntry(review: ReviewState): ReviewHistoryEntry {
  return {
    sessionId: review.sessionId,
    status: review.status,
    documentSource: inferDocumentSource(review),
    filename: review.filename,
    date: new Date().toLocaleString('zh-CN'),
    contractText: review.contractText,
    ocrWarnings: review.ocrWarnings,
    extractedInfo: review.extractedInfo,
    routingDecision: review.routingDecision,
    riskCards: review.riskCards,
    finalReport: review.finalReport,
    reviewStage: review.reviewStage,
    initialSummary: review.initialSummary,
    deepUpdateNotice: review.deepUpdateNotice,
    breakpointMessage: review.breakpointMessage,
    errorMessage: review.errorMessage,
    chatMessages: review.chatMessages,
  }
}

function buildHistoryOwnerCandidates(user?: { id?: string; email?: string | null } | null) {
  return [user?.id ?? null, user?.email ?? null]
}

function loadHistoryEntries(ownerKeys?: Array<string | null | undefined>): ReviewHistoryEntry[] {
  try {
    const entries = loadPersistedReviewHistoryFromOwners<ReviewHistoryEntry>(ownerKeys)
    return entries.map((entry) => ({
      ...entry,
      status: entry.status || 'complete',
      documentSource: inferDocumentSource(entry),
      filename: entry.filename || '未命名合同',
      contractText: entry.contractText || '',
      ocrWarnings: Array.isArray((entry as any).ocrWarnings)
        ? (entry as any).ocrWarnings.filter((item: unknown): item is string => typeof item === 'string')
        : [],
      riskCards: Array.isArray(entry.riskCards)
        ? entry.riskCards.map((card: any) => normalizeRiskCard(card))
        : [],
      finalReport: Array.isArray(entry.finalReport) ? entry.finalReport : [],
      reviewStage: entry.reviewStage || 'complete',
      initialSummary: entry.initialSummary || null,
      deepUpdateNotice: entry.deepUpdateNotice || null,
      chatMessages: Array.isArray(entry.chatMessages) && entry.chatMessages.length > 0
        ? entry.chatMessages.map((message: any) => normalizeChatMessage(message))
        : createDefaultChatMessages(),
    }))
  } catch {
    return []
  }
}

function saveHistoryEntry(entry: ReviewHistoryEntry, ownerKey?: string | null) {
  const history = loadHistoryEntries([ownerKey]).filter((item) => item.sessionId !== entry.sessionId)
  history.unshift(entry)
  if (history.length > 20) history.length = 20
  savePersistedReviewHistory(history, ownerKey)
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
  } else if (phase === 'initial_ready' || phase === 'deep_review') {
    statuses.parse = 'done'
    statuses.extract = 'done'
    statuses.retrieve = 'done'
    statuses.review = 'done'
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

export default function App() {
  const { isAuthenticated, login, logout, user, token, updateUser, refreshUser } = useAuth()

  // Resizable panels
  const [leftWidth, setLeftWidth] = useState(480)
  const isResizing = useRef(false)
  const workspaceRef = useRef<HTMLElement>(null)

  const handleResizerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isResizing.current = true
    const startX = e.clientX
    const startWidth = leftWidth

    const onMouseMove = (ev: MouseEvent) => {
      if (!isResizing.current) return
      const delta = ev.clientX - startX
      const newWidth = Math.max(280, Math.min(startWidth + delta, window.innerWidth - 320))
      setLeftWidth(newWidth)
    }
    const onMouseUp = () => {
      isResizing.current = false
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }, [leftWidth])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlToken = params.get('token')
    if (!urlToken) return
    const url = new URL(window.location.href)
    url.searchParams.delete('token')
    window.history.replaceState({}, '', url.toString())
    safeFetchJSON<{ user?: import('./contexts/AuthContext').User }>(apiPath('/auth/me'), {
      headers: { Authorization: `Bearer ${urlToken}` },
    })
      .then((data) => {
        if (data.user) login(urlToken, data.user)
      })
      .catch(() => {})
  }, [login])

  const historyOwnerKey = user?.id ?? null
  const historyOwnerCandidates = buildHistoryOwnerCandidates(user)
  const [authView, setAuthView] = useState<'landing' | 'login' | 'register' | 'forgot_password'>('landing')
  const [hasAcceptedDisclaimer, setHasAcceptedDisclaimer] = useState(() => loadDisclaimerAcceptance(historyOwnerKey))
  const [showSettings, setShowSettings] = useState(false)
  const [isExportingReport, setIsExportingReport] = useState(false)
  const [mobileDocVisible, setMobileDocVisible] = useState(false)
  const [review, setReview] = useState<ReviewState>(() => createInitialState(createSessionId()))
  const [streamContractText, setStreamContractText] = useState('')
  const [pendingReviewStart, setPendingReviewStart] = useState<PendingReviewStart | null>(null)
  const previousHistoryOwnerKeyRef = useRef<string | null>(historyOwnerKey)
  const prevPhaseRef = useRef<ReviewStatus>(review.status)
  const reviewRef = useRef(review)

  const hook = useStreamingReview(review.sessionId, streamContractText, {
    enabled: hasAcceptedDisclaimer && review.status === 'reviewing',
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
    if (previousHistoryOwnerKeyRef.current === historyOwnerKey) return
    previousHistoryOwnerKeyRef.current = historyOwnerKey
    setShowSettings(false)
    setPendingReviewStart(null)
    setHasAcceptedDisclaimer(loadDisclaimerAcceptance(historyOwnerKey))
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))
  }, [historyOwnerKey])

  useEffect(() => {
    if (!pendingReviewStart) return
    const sessionId = createSessionId()
    setStreamContractText(pendingReviewStart.text)
    setReview({
      ...createInitialState(sessionId),
      status: 'reviewing',
      sessionId,
      contractText: pendingReviewStart.text,
      filename: pendingReviewStart.filename,
    })
    setPendingReviewStart(null)
  }, [pendingReviewStart])

  useEffect(() => {
    if (!streamContractText) return

    setReview((prev) => {
      const nextExtractedInfo = mapEntities(hook.extractedEntities) ?? prev.extractedInfo
      const nextRoutingDecision = hook.routingDecision ?? prev.routingDecision
      const nextRiskCards = hook.issues.length > 0 ? mapIssues(hook.issues) : prev.riskCards
      const nextFinalReport = hook.reportParagraphs.length > 0 ? hook.reportParagraphs : prev.finalReport
      const nextReviewStage = hook.reviewStage === 'idle' ? prev.reviewStage : hook.reviewStage
      const nextInitialSummary = hook.reviewStage === 'initial' && hook.deepUpdateNotice
        ? hook.deepUpdateNotice
        : prev.initialSummary
      const nextDeepUpdateNotice = hook.deepUpdateNotice ?? prev.deepUpdateNotice
      const breakpointIssueCount = hook.breakpointData?.issues_count ?? hook.issues.length
      const nextStatus = hook.error
        ? 'error'
        : hook.phase === 'idle'
          ? prev.status
          : mapPhaseToStatus(hook.phase)
      const nextBreakpointMessage = hook.phase === 'breakpoint' && hook.breakpointData
        ? breakpointIssueCount > 0
          ? `已检测到 ${breakpointIssueCount} 处风险条款，请确认是否继续生成完整的避坑指南报告？`
          : '本次未检测到明显风险条款，是否继续生成完整的避坑指南报告？'
        : null

      return {
        ...prev,
        status: nextStatus,
        reviewStage: nextReviewStage,
        extractedInfo: nextExtractedInfo,
        routingDecision: nextRoutingDecision,
        riskCards: nextRiskCards,
        finalReport: nextFinalReport,
        initialSummary: nextInitialSummary,
        deepUpdateNotice: nextDeepUpdateNotice,
        breakpointMessage: hook.error ? hook.error : nextBreakpointMessage,
        errorMessage: hook.error || null,
        thinkingSteps: buildThinkingSteps(hook.phase, nextExtractedInfo, nextRoutingDecision),
      }
    })
  }, [
    hook.breakpointData,
    hook.deepUpdateNotice,
    hook.error,
    hook.extractedEntities,
    hook.issues,
    hook.phase,
    hook.reportParagraphs,
    hook.reviewStage,
    hook.routingDecision,
    streamContractText,
  ])

  useEffect(() => {
    if (hook.error) {
      void refreshUser()
    }
  }, [hook.error, refreshUser])

  useEffect(() => {
    const prevPhase = prevPhaseRef.current
    const shouldPersistOnPhaseEntry = ['breakpoint', 'error', 'complete'].includes(review.status)
    if (shouldPersistOnPhaseEntry && prevPhase !== review.status && review.filename && historyOwnerKey) {
      saveHistoryEntry(createHistoryEntry(reviewRef.current), historyOwnerKey)
      void refreshUser()
    }
    prevPhaseRef.current = review.status
  }, [historyOwnerKey, refreshUser, review.filename, review.status])

  const handleDisclaimerAccept = useCallback(() => {
    persistDisclaimerAcceptance(historyOwnerKey)
    setHasAcceptedDisclaimer(true)
  }, [historyOwnerKey])

  const openReviewDraft = useCallback((
    text: string,
    filename: string,
    options: {
      warnings?: string[]
      documentSource?: ReviewDocumentSource
    } = {},
  ) => {
    const {
      warnings = [],
      documentSource = 'ocr',
    } = options
    const nextSessionId = createSessionId()
    setMobileDocVisible(true)
    setStreamContractText('')
    setReview({
      ...createInitialState(nextSessionId),
      status: 'ocr_ready',
      sessionId: nextSessionId,
      documentSource,
      contractText: text,
      filename,
      ocrWarnings: warnings,
    })
  }, [])

  const startReview = useCallback((
    text: string,
    filename: string,
    documentSource: ReviewDocumentSource = 'direct',
  ) => {
    const sessionId = createSessionId()
    setMobileDocVisible(false)
    setStreamContractText(text)
    setReview({
      ...createInitialState(sessionId),
      status: 'reviewing',
      sessionId,
      documentSource,
      contractText: text,
      filename,
    })
  }, [])

  const handleFileUpload = useCallback((text: string, filename: string) => {
    openReviewDraft(text, filename, { documentSource: 'direct' })
  }, [openReviewDraft])

  const handleOcrReady = useCallback((text: string, filename: string, warnings: string[] = []) => {
    openReviewDraft(text, filename, { warnings, documentSource: 'ocr' })
  }, [openReviewDraft])

  const handleContractTextChange = useCallback((text: string) => {
    setReview((prev) => ({ ...prev, contractText: text }))
  }, [])

  const handleConfirmOcrReview = useCallback(() => {
    const text = review.contractText.trim()
    if (!text) {
      alert('请先确认识别出的合同文字后再开始分析。')
      return
    }
    startReview(text, review.filename, review.documentSource ?? 'ocr')
  }, [review.contractText, review.documentSource, review.filename, startReview])

  const handleBreakpointConfirm = useCallback(() => {
    hook.confirm()
  }, [hook])

  const handleRetryDeepReview = useCallback(() => {
    setReview((prev) => ({
      ...prev,
      status: 'reviewing',
      reviewStage: 'deep',
      deepUpdateNotice: '正在继续补全完整分析与报告...',
      errorMessage: null,
    }))
    hook.retryDeepReview({
      contractText: review.contractText,
      sessionId: review.sessionId,
      issues: mapRiskCardsToIssuePayload(review.riskCards),
    })
  }, [hook, review.contractText, review.riskCards, review.sessionId])

  const handleNewConversation = useCallback(() => {
    persistCurrentReview(review)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))
  }, [persistCurrentReview, review])

  const handleReset = useCallback(() => {
    setPendingReviewStart(null)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))
  }, [])

  const handleExportReport = useCallback(() => {
    const reportParagraphs = buildReportExportParagraphs(review)
    if (reportParagraphs.length === 0 || isExportingReport) return
    setIsExportingReport(true)
    exportReportAsWord({
      filename: review.filename,
      reportParagraphs,
      token,
    })
      .catch(() => alert('导出 Word 报告失败，请稍后重试。'))
      .finally(() => setIsExportingReport(false))
  }, [isExportingReport, review, token])

  const [isChatPending, setIsChatPending] = useState(false)
  const chatStreamRef = useRef<ReturnType<typeof createSSEClient> | null>(null)
  const activeAssistantMessageRef = useRef<string | null>(null)
  const chatReceivedTokenRef = useRef(false)

  const handleCancelChat = useCallback(() => {
    const activeAssistantId = activeAssistantMessageRef.current
    chatStreamRef.current?.abort()
    chatStreamRef.current = null
    activeAssistantMessageRef.current = null
    chatReceivedTokenRef.current = false
    setIsChatPending(false)

    if (!activeAssistantId) return

    setReview((prev) => ({
      ...prev,
      chatMessages: prev.chatMessages.flatMap((message) => {
        if (message.id !== activeAssistantId) return [message]
        if (!message.content.trim()) return []
        return [{ ...message, status: 'complete' as const }]
      }),
    }))
  }, [])

  const handleSendMessage = useCallback((message: string) => {
    const normalizedMessage = message.trim()
    if (!normalizedMessage) return

    const previousAssistantId = activeAssistantMessageRef.current
    chatStreamRef.current?.abort()
    chatStreamRef.current = null
    if (previousAssistantId) {
      setReview((prev) => ({
        ...prev,
        chatMessages: prev.chatMessages.flatMap((chatMessage) => {
          if (chatMessage.id !== previousAssistantId) return [chatMessage]
          if (!chatMessage.content.trim()) return []
          return [{ ...chatMessage, status: 'complete' as const }]
        }),
      }))
    }

    const userMsgId = `user-${Date.now()}`
    const assistantMsgId = `assistant-${Date.now() + 1}`
    activeAssistantMessageRef.current = assistantMsgId
    chatReceivedTokenRef.current = false

    setIsChatPending(true)
    setReview((prev) => ({
      ...prev,
      chatMessages: [
        ...prev.chatMessages,
        normalizeChatMessage({ id: userMsgId, role: 'user', content: normalizedMessage }),
        { id: assistantMsgId, role: 'assistant', content: '', status: 'retrieving' },
      ],
    }))

    const riskSummaryForStream = review.riskCards.map((card) => `[${card.level}] ${card.title}: ${card.issue}`).join('\n')
    const finishStream = () => {
      chatStreamRef.current = null
      activeAssistantMessageRef.current = null
      chatReceivedTokenRef.current = false
      setIsChatPending(false)
    }

    chatStreamRef.current = createSSEClient(
      apiPath('/chat/stream'),
      {
        message: normalizedMessage,
        contract_text: review.contractText,
        risk_summary: riskSummaryForStream,
        review_session_id: review.sessionId,
      },
      {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
      {
        onEvent: (event) => {
          if (event.event === 'chat_retrieval_started' || event.event === 'chat_retrieval_stage') {
            setReview((prev) => ({
              ...prev,
              chatMessages: prev.chatMessages.map((chatMessage) => (
                chatMessage.id === assistantMsgId
                  ? { ...chatMessage, status: 'retrieving' }
                  : chatMessage
              )),
            }))
            return
          }

          if (event.event === 'chat_retrieval_complete') {
            setReview((prev) => ({
              ...prev,
              chatMessages: prev.chatMessages.map((chatMessage) => (
                chatMessage.id === assistantMsgId
                  ? {
                    ...chatMessage,
                    content: chatReceivedTokenRef.current ? chatMessage.content : '',
                    status: 'streaming',
                  }
                  : chatMessage
              )),
            }))
            return
          }

          if (event.event === 'chat_token') {
            const tokenText = getStreamText(event.data, 'text')
            if (!tokenText) return
            chatReceivedTokenRef.current = true
            setReview((prev) => ({
              ...prev,
              chatMessages: prev.chatMessages.map((chatMessage) => (
                chatMessage.id === assistantMsgId
                  ? { ...chatMessage, content: `${chatMessage.content}${tokenText}`, status: 'streaming' }
                  : chatMessage
              )),
            }))
            return
          }

          if (event.event === 'error') {
            const errorMessage = getStreamText(event.data, 'message') || '聊天请求失败，请稍后重试。'
            const isPartial = Boolean(
              event.data
              && typeof event.data === 'object'
              && (event.data as Record<string, unknown>).partial
            )
            setReview((prev) => ({
              ...prev,
              chatMessages: prev.chatMessages.map((chatMessage) => {
                if (chatMessage.id !== assistantMsgId) return chatMessage
                const nextContent = isPartial && chatMessage.content.trim()
                  ? `${chatMessage.content}\n\n${errorMessage}`
                  : errorMessage
                return { ...chatMessage, content: nextContent, status: 'error' }
              }),
            }))
            finishStream()
            return
          }

          if (event.event === 'chat_complete') {
            setReview((prev) => ({
              ...prev,
              chatMessages: prev.chatMessages.map((chatMessage) => (
                chatMessage.id === assistantMsgId
                  ? {
                    ...chatMessage,
                    status: chatMessage.content.trim() ? 'complete' : 'error',
                    content: chatMessage.content.trim() || '未获得可用回答，请稍后重试。',
                  }
                  : chatMessage
              )),
            }))
            finishStream()
          }
        },
        onError: (error) => {
          const errorMessage = error instanceof Error ? error.message : '聊天请求失败，请稍后重试。'
          const isExpired = error instanceof Error && /401|expired|login/i.test(error.message)
          if (isExpired) {
            finishStream()
            logout()
            return
          }
          setReview((prev) => ({
            ...prev,
            chatMessages: prev.chatMessages.map((chatMessage) => (
              chatMessage.id === assistantMsgId
                ? {
                  ...chatMessage,
                  content: chatReceivedTokenRef.current && chatMessage.content.trim()
                    ? `${chatMessage.content}\n\n${errorMessage}`
                    : errorMessage,
                  status: 'error',
                }
                : chatMessage
            )),
          }))
          finishStream()
        },
      },
    )
    return

/*
      const riskSummary = review.riskCards.map((card) => `[${card.level}] ${card.title}: ${card.issue}`).join('\n')
      const payload = await safeFetchJSON<{ reply?: string; error?: string }>(apiPath('/chat'), {
        method: 'POST',
        signal: abortController.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: normalizedMessage,
          contract_text: review.contractText,
          risk_summary: riskSummary,
          review_session_id: review.sessionId,
        }),
      })

      setReview((prev) => ({
        ...prev,
        chatMessages: prev.chatMessages.map((chatMessage) => (
          chatMessage.id === assistantMsgId
            ? { ...chatMessage, content: normalizeAssistantReply(payload.reply) }
            : chatMessage
        )),
      }))
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // Remove the pending assistant bubble on cancel
        setReview((prev) => ({
          ...prev,
          chatMessages: prev.chatMessages.filter((m) => m.id !== assistantMsgId),
        }))
      } else {
        const errorMessage = err instanceof Error ? err.message : '网络错误，请重试。'
        // Auto-logout on expired token
        if (err instanceof Error && err.message.includes('登录已过期')) {
          logout()
          return
        }
        setReview((prev) => ({
          ...prev,
          chatMessages: prev.chatMessages.map((chatMessage) => (
            chatMessage.id === assistantMsgId
              ? { ...chatMessage, content: errorMessage }
              : chatMessage
          )),
        }))
      }
    } finally {
      setIsChatPending(false)
    }
*/
  }, [logout, review.contractText, review.riskCards, review.sessionId, token])

  const handleSelectHistorySession = useCallback((sessionId: string) => {
    const entry = loadHistoryEntries(historyOwnerCandidates).find((item) => item.sessionId === sessionId)
    if (!entry) return
    if (review.sessionId !== sessionId) {
      persistCurrentReview(review)
    }
    setStreamContractText('')
    setReview({
      ...createInitialState(entry.sessionId),
      status: entry.status,
      reviewStage: entry.reviewStage || 'complete',
      sessionId: entry.sessionId,
      documentSource: entry.documentSource ?? inferDocumentSource(entry),
      contractText: entry.contractText,
      filename: entry.filename,
      ocrWarnings: entry.ocrWarnings,
      extractedInfo: entry.extractedInfo,
      routingDecision: entry.routingDecision,
      riskCards: entry.riskCards,
      finalReport: entry.finalReport,
      initialSummary: entry.initialSummary || null,
      deepUpdateNotice: entry.deepUpdateNotice || null,
      breakpointMessage: entry.breakpointMessage,
      errorMessage: entry.errorMessage,
      chatMessages: entry.chatMessages?.length
        ? entry.chatMessages.map((message) => normalizeChatMessage(message))
        : createDefaultChatMessages(),
      thinkingSteps: buildThinkingSteps(entry.status, entry.extractedInfo, entry.routingDecision),
    })
  }, [historyOwnerCandidates, persistCurrentReview, review])

  const handleDeleteHistorySession = useCallback((sessionId: string) => {
    if (review.sessionId !== sessionId) return
    setPendingReviewStart(null)
    setStreamContractText('')
    setReview(createInitialState(createSessionId()))
  }, [review.sessionId])

  if (!isAuthenticated) {
    if (authView === 'landing') {
      return (
        <LandingPage
          onNavigateLogin={() => setAuthView('login')}
          onNavigateRegister={() => setAuthView('register')}
        />
      )
    }
    if (authView === 'register') {
      return <RegisterPage onNavigateLogin={() => setAuthView('login')} />
    }
    if (authView === 'forgot_password') {
      return <ForgotPasswordPage onNavigateLogin={() => setAuthView('login')} />
    }
    return (
      <LoginPage
        onLogin={login}
        onNavigateRegister={() => setAuthView('register')}
        onNavigateForgotPassword={() => setAuthView('forgot_password')}
        onNavigateLanding={() => setAuthView('landing')}
      />
    )
  }

  if (!hasAcceptedDisclaimer) {
    return <DisclaimerModal onAccept={handleDisclaimerAccept} />
  }

  if (showSettings && user && token) {
    return <SettingsPage user={user} token={token} onUserUpdate={updateUser} onBack={() => setShowSettings(false)} />
  }

  return (
    <div className="app-layout">
      <SideNav
        user={user}
        onLogout={logout}
        onSelectHistorySession={handleSelectHistorySession}
        onDeleteHistorySession={handleDeleteHistorySession}
        onOpenSettings={() => setShowSettings(true)}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div className="mobile-panel-tabs">
          <button
            type="button"
            className={`mobile-panel-tab${!mobileDocVisible ? ' mobile-panel-tab--active' : ''}`}
            onClick={() => setMobileDocVisible(false)}
          >
            💬 对话
          </button>
          <button
            type="button"
            className={`mobile-panel-tab${mobileDocVisible ? ' mobile-panel-tab--active' : ''}`}
            onClick={() => setMobileDocVisible(true)}
          >
            📄 合同
          </button>
        </div>
        <main className="workspace" ref={workspaceRef} style={{ gridTemplateColumns: `${leftWidth}px 6px 1fr` }}>
          <div className={mobileDocVisible ? 'workspace__panel--hidden' : undefined}>
            <ChatPanel
              review={review}
              authToken={token}
              onBreakpointConfirm={handleBreakpointConfirm}
              canRetryDeepReview={hook.canRetryDeepReview}
              onRetryDeepReview={handleRetryDeepReview}
              onReset={handleReset}
              onSendMessage={handleSendMessage}
              isChatPending={isChatPending}
              onCancelChat={handleCancelChat}
            />
          </div>
          <div className="workspace__resizer" onMouseDown={handleResizerMouseDown} />
          <div className={!mobileDocVisible ? 'workspace__panel--hidden' : undefined}>
            <DocPanel
              review={review}
              authToken={token}
              canExportReport={canExportReviewReport(review)}
              onExportReport={handleExportReport}
              isExportingReport={isExportingReport}
              onFileUpload={handleFileUpload}
              onOcrReady={handleOcrReady}
              onContractTextChange={handleContractTextChange}
              onConfirmReview={handleConfirmOcrReview}
              onReset={handleReset}
              onNewConversation={handleNewConversation}
            />
          </div>
        </main>
      </div>
      {review.status === 'reviewing' && (
        <button className="fab" onClick={handleReset}>
          重新扫描
        </button>
      )}
    </div>
  )
}
