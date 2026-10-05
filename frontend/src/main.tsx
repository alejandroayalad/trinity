import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tokens.css'
import './styles/base.css'

// Temporary entry point for the foundations slice. Step 3 replaces it with
// the session, router and application shell.
createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <main className="page-enter" style={{ padding: 'var(--content-padding)' }}>
      <h1>Trinity</h1>
    </main>
  </StrictMode>,
)
