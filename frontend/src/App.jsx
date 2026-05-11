import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import TestRunView from './pages/TestRunView'
import AIConfig from './pages/AIConfig'
import JenkinsConfig from './pages/JenkinsConfig'
import SecurityConfig from './pages/SecurityConfig'

import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  return (
    <ErrorBoundary>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#0f1923',
            color: '#e0e8f0',
            border: '1px solid rgba(0,229,255,0.15)',
            fontSize: 13,
            borderRadius: 8,
          },
          success: { iconTheme: { primary: '#00e676', secondary: '#0f1923' } },
          error: { iconTheme: { primary: '#ff1744', secondary: '#0f1923' } },
        }}
      />
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="test-runs" element={<TestRunView />} />
          <Route path="ai-config" element={<AIConfig />} />
          <Route path="jenkins" element={<JenkinsConfig />} />
          <Route path="security" element={<SecurityConfig />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}
