import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
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
      <main className="container">
        <h1>Resume Tailor</h1>
        <p role="alert" className="error">
          The app is not configured. For local development copy <code>public/config.example.json</code> to{' '}
          <code>public/config.json</code> and fill in the stack outputs.
        </p>
      </main>,
    )
  })
