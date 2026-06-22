import { type ReactElement } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { LanguageProvider } from '../contexts/LanguageContext'

function AllProviders({ children }: { children: React.ReactNode }) {
  return <LanguageProvider>{children}</LanguageProvider>
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AllProviders, ...options })
}
