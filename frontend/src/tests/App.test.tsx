import { describe, expect, it } from 'vitest'
import { buildThinkingSteps } from '../App'

describe('buildThinkingSteps', () => {
  it('marks parse as active when the stream just started', () => {
    expect(buildThinkingSteps('started', null, null).map((step) => step.status)).toEqual([
      'active',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('marks extraction as active during entity extraction', () => {
    expect(buildThinkingSteps('extraction', null, null).map((step) => step.status)).toEqual([
      'done',
      'active',
      'pending',
      'pending',
    ])
  })

  it('marks all steps as done after completion', () => {
    expect(buildThinkingSteps('complete', null, null).map((step) => step.status)).toEqual([
      'done',
      'done',
      'done',
      'done',
    ])
  })
})
