import { createRoot } from 'react-dom/client'
import App from './App'
import { loadConfig } from './auth'
import './styles.css'

loadConfig().then(() => createRoot(document.getElementById('root')!).render(<App />))
