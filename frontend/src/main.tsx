import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SessionProvider } from './session/SessionProvider'
import { App } from './App'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'

// Commands never retry implicitly. Pages choose safe retries explicitly.
const cache = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } })
createRoot(document.getElementById('root') as HTMLElement).render(<StrictMode><QueryClientProvider client={cache}><BrowserRouter><SessionProvider><App /></SessionProvider></BrowserRouter></QueryClientProvider></StrictMode>)
