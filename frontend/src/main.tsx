import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/index.css'
import App from './App.tsx'
import { configureAuth } from './auth/cognito'
import { loadConfig } from './config'

const root = createRoot(document.getElementById('root')!)

loadConfig()
  .then((config) => {
    configureAuth(config)
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
  })
  .catch(() => {
    root.render(
      <main className="container main">
        <div className="alert alert-error" role="alert">
          The app is not configured. For local development, copy <code>public/config.example.json</code> to{' '}
          <code>public/config.json</code> and fill in the stack outputs.
        </div>
      </main>,
    )
  })
