const INVISIBLE_TEXT_PATTERN = /[\u200b\u200c\u200d\u2060\ufeff]/g
const THINK_BLOCK_PATTERN = /<think>[\s\S]*?<\/think>/gi
const THINK_TAG_PATTERN = /<\/?think>/gi

export const EMPTY_ASSISTANT_REPLY_TEXT = '模型没有返回可见内容，请再试一次。'

export function normalizeAssistantReply(reply: unknown) {
  if (typeof reply !== 'string') {
    return EMPTY_ASSISTANT_REPLY_TEXT
  }

  const normalized = reply
    .replace(THINK_BLOCK_PATTERN, '')
    .replace(THINK_TAG_PATTERN, '')
    .replace(INVISIBLE_TEXT_PATTERN, '')
    .trim()
  return normalized || EMPTY_ASSISTANT_REPLY_TEXT
}
