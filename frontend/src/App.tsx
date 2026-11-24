import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/context'
import { AppFooter } from './components/layout/AppFooter'
import { AppHeader } from './components/layout/AppHeader'
import { Spinner } from './components/ui/Spinner'
import { AuthPage } from './features/auth/AuthPage'
import { TailorPage } from './features/tailor/TailorPage'

function Screen() {
  const { status } = useAuth()
  if (status === 'loading') {
    return (
      <div className="center-screen">
        <Spinner label="Loading" />
      </div>
    )
  }
  return status === 'signedIn' ? <TailorPage /> : <AuthPage />
}

export default function App() {
  return (
    <AuthProvider>
      <div className="app">
        <AppHeader />
        <main className="container main">
          <Screen />
        </main>
        <AppFooter />
      </div>
    </AuthProvider>
  )
}
