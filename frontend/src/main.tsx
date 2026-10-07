import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { shouldRetry, retryDelay } from './api/retry'
import { SessionProvider } from './session/SessionProvider'
import { App } from './App'
import { ToastProvider } from './components/feedback/Toast'
import './styles/tokens.css'
import './styles/base.css'

// Commands never retry implicitly. Reads retry once only for a short
// rate-limit wait; every other failure waits for the user's Retry button.
const cache = new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, retryDelay, refetchOnWindowFocus: false }, mutations: { retry: false } } })
createRoot(document.getElementById('root') as HTMLElement).render(<StrictMode><QueryClientProvider client={cache}><BrowserRouter><SessionProvider><ToastProvider><App /></ToastProvider></SessionProvider></BrowserRouter></QueryClientProvider></StrictMode>)
