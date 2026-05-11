import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  Activity, Layers, Play, Cpu,
  Shield, ChevronLeft, ChevronRight,
  GitBranch, Bot,
} from 'lucide-react'

const menuItems = [
  { path: '/', icon: Activity, label: '仪表盘', color: '#00e5ff' },
  { path: '/projects', icon: Layers, label: '项目管理', color: '#448aff' },
  { path: '/ai-config', icon: Cpu, label: 'AI 配置', color: '#e040fb' },
  { path: '/test-runs', icon: Play, label: '测试运行', color: '#00e676' },
  { path: '/jenkins', icon: GitBranch, label: 'Jenkins', color: '#ff9100' },
  { path: '/security', icon: Shield, label: '安全设置', color: '#ff1744' },
]

export default function Sidebar({ collapsed, onToggle }) {
  const location = useLocation()

  return (
    <div
      className="h-screen flex flex-col border-r transition-all duration-300"
      style={{
        width: collapsed ? 64 : 240,
        background: 'linear-gradient(180deg, #0a0e1a 0%, #0f1923 100%)',
        borderColor: 'rgba(0, 229, 255, 0.08)',
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-3 px-4 h-16 border-b"
        style={{ borderColor: 'rgba(0, 229, 255, 0.08)' }}
      >
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{
            background: 'linear-gradient(135deg, rgba(0,229,255,0.2), rgba(224,64,251,0.2))',
            border: '1px solid rgba(0,229,255,0.3)',
          }}
        >
          <Bot size={18} style={{ color: '#00e5ff' }} />
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e0e8f0', whiteSpace: 'nowrap' }}>
              自动测试平台
            </div>
            <div style={{ fontSize: 10, color: '#556677', whiteSpace: 'nowrap' }}>AI Test Platform</div>
          </div>
        )}
      </div>

      {/* 菜单 */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {menuItems.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path))
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group"
              style={{
                background: isActive ? 'rgba(0,229,255,0.08)' : 'transparent',
                color: isActive ? item.color : '#8899aa',
                borderLeft: isActive ? `2px solid ${item.color}` : '2px solid transparent',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'rgba(0,229,255,0.03)'
                  e.currentTarget.style.color = '#e0e8f0'
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = '#8899aa'
                }
              }}
            >
              <item.icon size={18} />
              {!collapsed && <span style={{ fontSize: 13, whiteSpace: 'nowrap' }}>{item.label}</span>}
            </NavLink>
          )
        })}
      </nav>

      {/* 底部折叠按钮 */}
      <div className="px-2 py-3 border-t" style={{ borderColor: 'rgba(0, 229, 255, 0.08)' }}>
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg transition-all"
          style={{ color: '#556677' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#00e5ff'; e.currentTarget.style.background = 'rgba(0,229,255,0.05)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#556677'; e.currentTarget.style.background = 'transparent' }}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          {!collapsed && <span style={{ fontSize: 12 }}>折叠</span>}
        </button>
      </div>
    </div>
  )
}
