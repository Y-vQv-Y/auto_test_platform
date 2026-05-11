import React, { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen" style={{ background: '#0a0e1a' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <main className="flex-1 overflow-y-auto grid-bg" style={{ minWidth: 0 }}>
        {/* 顶部状态栏 */}
        <div
          className="flex items-center justify-between px-6 py-3 border-b sticky top-0 z-10"
          style={{
            background: 'rgba(10, 14, 26, 0.8)',
            backdropFilter: 'blur(12px)',
            borderColor: 'rgba(0, 229, 255, 0.08)',
          }}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background: '#00e676', boxShadow: '0 0 6px #00e676' }} />
              <span style={{ fontSize: 12, color: '#00e676' }}>系统运行中</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span style={{ fontSize: 12, color: '#556677' }}>AI 自动测试平台 v1.0.0</span>
          </div>
        </div>

        {/* 页面内容 */}
        <div style={{ padding: 24 }}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
