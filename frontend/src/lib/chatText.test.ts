import { describe, expect, it } from 'vitest'
import { EMPTY_ASSISTANT_REPLY_TEXT, normalizeAssistantReply } from './chatText'

describe('normalizeAssistantReply', () => {
  it('keeps visible assistant replies and trims surrounding whitespace', () => {
    expect(normalizeAssistantReply('\n  这是可见回复。  \n')).toBe('这是可见回复。')
  })

  it('falls back when the reply only contains invisible characters', () => {
    expect(normalizeAssistantReply('\u200b\n\ufeff')).toBe(EMPTY_ASSISTANT_REPLY_TEXT)
  })

  it('falls back when the reply is missing or not text', () => {
    expect(normalizeAssistantReply(undefined)).toBe(EMPTY_ASSISTANT_REPLY_TEXT)
  })
})
