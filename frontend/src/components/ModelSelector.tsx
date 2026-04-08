import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import type { ModelKey, ModelOption } from '../App'

interface ModelSelectorProps {
  selectedModel: ModelKey
  availableModels: ModelOption[]
  onModelChange: (model: ModelKey) => void
  label?: string
  menuPlacement?: 'top' | 'bottom'
}

export function ModelSelector({
  selectedModel,
  availableModels,
  onModelChange,
  label = '模型',
  menuPlacement = 'top',
}: ModelSelectorProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selectedModelOption = availableModels.find((option) => option.key === selectedModel)

  useEffect(() => {
    if (!isMenuOpen) return

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
    }
  }, [isMenuOpen])

  useEffect(() => {
    setIsMenuOpen(false)
  }, [selectedModel])

  return (
    <div
      className={`model-select ${menuPlacement === 'bottom' ? 'model-select--bottom' : ''}`}
      ref={rootRef}
    >
      <button
        type="button"
        className="model-select__trigger"
        aria-haspopup="listbox"
        aria-expanded={isMenuOpen}
        onClick={() => setIsMenuOpen((value) => !value)}
      >
        <span className="model-select__label">{label}</span>
        <span className="model-select__value">{selectedModelOption?.label ?? selectedModel}</span>
        <ChevronDown size={16} />
      </button>
      {isMenuOpen && (
        <div className="model-select__menu" role="listbox" aria-label={`选择${label}`}>
          {availableModels.map((option) => (
            <button
              key={option.key}
              type="button"
              role="option"
              aria-selected={option.key === selectedModel}
              className={`model-select__option ${
                option.key === selectedModel ? 'model-select__option--active' : ''
              }`}
              onClick={() => {
                onModelChange(option.key)
                setIsMenuOpen(false)
              }}
            >
              <span>{option.label}</span>
              {option.key === selectedModel && <Check size={16} className="model-select__check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
