import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './hooks/AuthContext'
import { AppLayout } from './layouts/AppLayout'
import {
  AssistantPage,
  CertificationGuidePage,
  DocumentManagerPage,
  HistoryPage,
  HomePage,
  LabDirectoryPage,
  NotFoundPage,
  SettingsPage,
  StandardDetailPage,
  StandardsExplorerPage,
} from './pages'

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="standards" element={<StandardsExplorerPage />} />
            <Route path="standards/:id" element={<StandardDetailPage />} />
            <Route path="certification" element={<CertificationGuidePage />} />
            <Route path="labs" element={<LabDirectoryPage />} />
            <Route path="documents" element={<DocumentManagerPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
