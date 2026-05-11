import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { systemApi, testRunApi } from '../api'
import {
  Activity, Layers, TestTube, Cpu, Play,
  CheckCircle, XCircle, Clock, ArrowRight,
  BarChart3, TrendingUp, Server,
} from 'lucide-react'

const statusColors = {
  passed: '#00e676', failed: '#ff1744', running: '#00e5ff',
  pending: '#8899aa', error: '#ff9100', cancelled: '#ff9100',
}
const statusIcons = {
  passed: CheckCircle, failed: XCircle, running: Activity,
  pending: Clock, error: XCircle, cancelled: XCircle,
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [dashboard, recentRuns] = await Promise.all([
        systemApi.dashboard(),
        testRunApi.list({ page_size: 10 }),
      ])
      setData({ ...dashboard, recentRuns: recentRuns.items || [] })
    } catch (err) {
      console.error('加载仪表盘数据失败:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="loading-spinner" />
      </div>
    )
  }

  const stats = data?.stats || {}
  const statusDist = data?.status_distribution || {}
  const recentRuns = data?.recentRuns || []

  const statCards = [
    { label: '项目总数', value: stats.total_projects || 0, icon: Layers, color: '#448aff' },
    { label: '测试运行', value: stats.total_test_runs || 0, icon: Play, color: '#00e5ff' },
    { label: '测试用例', value: stats.total_test_cases || 0, icon: TestTube, color: '#e040fb' },
    { label: 'AI 配置', value: stats.total_ai_configs || 0, icon: Cpu, color: '#00e676' },
    { label: '本周运行', value: stats.weekly_runs || 0, icon: BarChart3, color: '#ff9100' },
    { label: '成功率', value: `${stats.success_rate || 0}%`, icon: TrendingUp, color: stats.success_rate > 80 ? '#00e676' : '#ff9100' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      {/* 标题 */}
      <div>
        <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>
          控制台
        </h1>
        <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>AI 自动测试平台运行状态总览</p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((card, idx) => (
          <div
            key={idx}
            className="cyber-card p-4 animate-slide-up cursor-pointer transition-all hover:translate-y-[-2px]"
            style={{ animationDelay: `${idx * 0.05}s` }}
            onClick={() => {
              if (idx === 0) navigate('/projects')
              if (idx === 3) navigate('/ai-config')
              if (idx === 1) navigate('/test-runs')
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <card.icon size={20} style={{ color: card.color }} />
            </div>
            <div className="text-2xl font-bold mb-1" style={{ color: card.color }}>
              {card.value}
            </div>
            <div style={{ fontSize: 12, color: '#8899aa' }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* 状态分布 + 最近运行 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 状态分布 */}
        <div className="cyber-card p-5 lg:col-span-1">
          <h3 className="text-sm font-semibold mb-4" style={{ color: '#00e5ff' }}>运行状态分布</h3>
          <div className="space-y-3">
            {[
              { key: 'passed', label: '通过', color: '#00e676' },
              { key: 'failed', label: '失败', color: '#ff1744' },
              { key: 'running', label: '运行中', color: '#00e5ff' },
              { key: 'pending', label: '等待中', color: '#8899aa' },
              { key: 'error', label: '错误', color: '#ff9100' },
            ].map((item) => {
              const count = statusDist[item.key] || 0
              const total = Object.values(statusDist).reduce((a, b) => a + b, 0) || 1
              const pct = Math.round((count / total) * 100)
              return (
                <div key={item.key}>
                  <div className="flex justify-between text-xs mb-1">
                    <span style={{ color: '#8899aa' }}>{item.label}</span>
                    <span style={{ color: item.color }}>{count}</span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${pct}%`, background: item.color }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 最近测试运行 */}
        <div className="cyber-card p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold" style={{ color: '#00e5ff' }}>最近测试运行</h3>
            <button className="cyber-button text-xs" onClick={() => navigate('/test-runs')}>
              查看全部 <ArrowRight size={14} />
            </button>
          </div>

          {recentRuns.length === 0 ? (
            <div className="text-center py-8" style={{ color: '#556677' }}>
              <Activity size={32} className="mx-auto mb-2" />
              <p style={{ fontSize: 13 }}>暂无测试运行记录</p>
            </div>
          ) : (
            <div className="space-y-2">
              {recentRuns.map((run) => {
                const StatusIcon = statusIcons[run.status] || Activity
                return (
                  <div
                    key={run.id}
                    className="flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all"
                    style={{ background: 'rgba(0,0,0,0.2)' }}
                    onClick={() => navigate(`/test-runs?id=${run.id}`)}
                    onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,229,255,0.03)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.2)' }}
                  >
                    <div className="flex items-center gap-3">
                      <StatusIcon size={16} style={{ color: statusColors[run.status] || '#8899aa' }} />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500 }}>{run.name || `测试运行 #${run.id}`}</div>
                        <div style={{ fontSize: 11, color: '#556677' }}>
                          {new Date(run.created_at).toLocaleString('zh-CN')}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span style={{ fontSize: 11, color: '#556677' }}>
                        {run.total_cases || 0} 用例
                      </span>
                      <span className={`status-badge ${run.status}`}>{run.status}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
