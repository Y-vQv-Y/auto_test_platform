import React, { useState, useEffect } from 'react'
import { systemApi } from '../api'
import {
  Shield, Globe, Lock, Eye, RefreshCw,
  CheckCircle, XCircle, AlertTriangle, FileWarning,
} from 'lucide-react'
import toast from 'react-hot-toast'

export default function SecurityConfig() {
  const [settings, setSettings] = useState(null)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [whitelistInput, setWhitelistInput] = useState('')

  useEffect(() => { loadData() }, [])

  async function loadData() {
    try {
      const [sec, logsRes] = await Promise.all([
        systemApi.securitySettings(),
        systemApi.securityLogs({ page_size: 50 }),
      ])
      setSettings(sec)
      setLogs(logsRes.items || [])
    } catch (err) {
      toast.error('加载安全配置失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleAddUrl() {
    if (!whitelistInput.trim()) return
    const urls = [...(settings?.url_whitelist || []), whitelistInput.trim()]
    try {
      await systemApi.updateUrlWhitelist(urls)
      setSettings(prev => ({ ...prev, url_whitelist: urls }))
      setWhitelistInput('')
      toast.success('URL 已添加到白名单')
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleRemoveUrl(url) {
    const urls = (settings?.url_whitelist || []).filter(u => u !== url)
    try {
      await systemApi.updateUrlWhitelist(urls)
      setSettings(prev => ({ ...prev, url_whitelist: urls }))
      toast.success('URL 已移除')
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function toggleUrlWhitelist() {
    const newVal = !settings?.url_whitelist_enabled
    try {
      await systemApi.updateUrlWhitelistToggle(newVal)
      setSettings(prev => ({ ...prev, url_whitelist_enabled: newVal }))
      toast.success(`URL 白名单已${newVal ? '开启' : '关闭'}`)
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function toggleReadonly() {
    const newVal = !settings?.readonly_mode
    try {
      await systemApi.updateReadonlyMode(newVal)
      setSettings(prev => ({ ...prev, readonly_mode: newVal }))
      toast.success(`只读模式已${newVal ? '开启' : '关闭'}`)
    } catch (err) {
      toast.error(err.message)
    }
  }

  if (loading) {
    return <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
  }

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>安全设置</h1>
        <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>
          URL 校验、工具白名单、只读模式、自动回滚等安全控制
        </p>
      </div>

      {/* 安全开关 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="cyber-card p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Shield size={18} style={{ color: '#00e5ff' }} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>只读模式</span>
            </div>
            <button
              onClick={toggleReadonly}
              className="w-10 h-5 rounded-full relative transition-all cursor-pointer"
              style={{
                background: settings?.readonly_mode ? 'rgba(0,229,255,0.3)' : 'rgba(136,153,170,0.2)',
              }}
            >
              <div className="w-3.5 h-3.5 rounded-full absolute top-0.5 transition-all"
                style={{
                  left: settings?.readonly_mode ? 22 : 3,
                  background: settings?.readonly_mode ? '#00e5ff' : '#8899aa',
                }} />
            </button>
          </div>
          <p style={{ fontSize: 12, color: '#8899aa' }}>
            启用后，测试执行时将禁止所有写操作（点击、输入、文件上传等）
          </p>
          <div className="mt-3 flex items-center gap-1" style={{ fontSize: 11, color: settings?.readonly_mode ? '#00e676' : '#556677' }}>
            {settings?.readonly_mode ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {settings?.readonly_mode ? '只读模式已激活' : '读写模式'}
          </div>
        </div>

        <div className="cyber-card p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Lock size={18} style={{ color: '#e040fb' }} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>自动回滚</span>
            </div>
            <button
              className="w-10 h-5 rounded-full relative transition-all cursor-not-allowed"
              style={{ background: settings?.auto_rollback_enabled ? 'rgba(224,64,251,0.3)' : 'rgba(136,153,170,0.2)' }}
            >
              <div className="w-3.5 h-3.5 rounded-full absolute top-0.5 transition-all"
                style={{
                  left: settings?.auto_rollback_enabled ? 22 : 3,
                  background: settings?.auto_rollback_enabled ? '#e040fb' : '#8899aa',
                }} />
            </button>
          </div>
          <p style={{ fontSize: 12, color: '#8899aa' }}>
            测试异常时自动恢复环境到初始状态
          </p>
          <div className="mt-3 flex items-center gap-1" style={{ fontSize: 11, color: '#556677' }}>
            {settings?.auto_rollback_enabled ? '已启用' : '已禁用'}
          </div>
        </div>

        <div className="cyber-card p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Eye size={18} style={{ color: '#00e676' }} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>工具白名单</span>
            </div>
            <span className="status-badge passed" style={{ fontSize: 11 }}>
              {settings?.tool_whitelist_enabled ? '已启用' : '已禁用'}
            </span>
          </div>
          <p style={{ fontSize: 12, color: '#8899aa' }}>
            控制测试脚本可以使用的 Playwright 操作，禁止危险操作
          </p>
          {settings?.default_tool_blocked && (
            <details className="mt-3">
              <summary style={{ fontSize: 11, color: '#ff1744', cursor: 'pointer' }}>
                查看禁止的操作 ({settings.default_tool_blocked.length}项)
              </summary>
              <div className="mt-2 flex flex-wrap gap-1">
                {settings.default_tool_blocked.map(t => (
                  <span key={t} className="status-badge error" style={{ fontSize: 10 }}>{t}</span>
                ))}
              </div>
            </details>
          )}
        </div>
      </div>

      {/* URL 白名单 */}
      <div className="cyber-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Globe size={18} style={{ color: '#448aff' }} />
            <h3 className="text-sm font-semibold" style={{ color: '#448aff' }}>URL 白名单</h3>
          </div>
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 11, color: settings?.url_whitelist_enabled ? '#00e676' : '#8899aa' }}>
              {settings?.url_whitelist_enabled ? '已启用' : '已关闭'}
            </span>
            <button
              onClick={toggleUrlWhitelist}
              className="w-10 h-5 rounded-full relative transition-all cursor-pointer"
              style={{
                background: settings?.url_whitelist_enabled ? 'rgba(68,138,255,0.3)' : 'rgba(136,153,170,0.2)',
              }}
            >
              <div className="w-3.5 h-3.5 rounded-full absolute top-0.5 transition-all"
                style={{
                  left: settings?.url_whitelist_enabled ? 22 : 3,
                  background: settings?.url_whitelist_enabled ? '#448aff' : '#8899aa',
                }} />
            </button>
          </div>
        </div>
        <p style={{ fontSize: 12, color: '#8899aa', marginBottom: 12 }}>
          {settings?.url_whitelist_enabled
            ? '启用后，只有白名单中的 URL 可以被测试脚本访问'
            : '已关闭 — 所有 HTTP/HTTPS URL 均可访问'}
          <br />
          <span style={{ color: '#556677' }}>关闭时白名单配置保留，但不会生效</span>
        </p>

        {settings?.url_whitelist_enabled && (
          <>
            <div className="flex gap-2 mb-4">
              <input
                className="cyber-input flex-1"
                placeholder="输入允许的 URL，例如 https://example.com"
                value={whitelistInput}
                onChange={(e) => setWhitelistInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddUrl()}
              />
              <button className="cyber-button" onClick={handleAddUrl}>添加</button>
            </div>

            {(settings?.url_whitelist || []).length === 0 ? (
              <div style={{ fontSize: 12, color: '#556677', padding: 16, textAlign: 'center' }}>
                <AlertTriangle size={20} className="mx-auto mb-1" />
                暂无 URL 白名单 — 添加 URL 到白名单以允许访问
              </div>
            ) : (
              <div className="space-y-2">
                {settings.url_whitelist.map((url, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded-lg"
                    style={{ background: 'rgba(0,0,0,0.2)' }}>
                    <div className="flex items-center gap-2">
                      <CheckCircle size={12} style={{ color: '#00e676' }} />
                      <span style={{ fontSize: 13 }}>{url}</span>
                    </div>
                    <button
                      className="p-1 rounded transition-all"
                      style={{ color: '#556677' }}
                      onClick={() => handleRemoveUrl(url)}
                      onMouseEnter={(e) => e.currentTarget.style.color = '#ff1744'}
                      onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
                    >
                      <XCircle size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* 安全日志 */}
      <div className="cyber-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FileWarning size={18} style={{ color: '#ff9100' }} />
            <h3 className="text-sm font-semibold" style={{ color: '#ff9100' }}>安全日志</h3>
          </div>
          <button className="cyber-button text-xs" onClick={loadData}>
            <RefreshCw size={12} /> 刷新
          </button>
        </div>

        {logs.length === 0 ? (
          <div style={{ fontSize: 12, color: '#556677', padding: 16, textAlign: 'center' }}>
            暂无安全日志
          </div>
        ) : (
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {logs.map(log => (
              <div key={log.id} className="flex items-start gap-3 p-2 rounded-lg text-xs"
                style={{ background: 'rgba(0,0,0,0.15)' }}>
                <span className={`status-badge ${log.result === 'allowed' ? 'passed' : 'failed'}`}
                  style={{ fontSize: 10, flexShrink: 0 }}>
                  {log.result}
                </span>
                <div className="flex-1 min-w-0">
                  <div style={{ color: '#8899aa' }}>
                    <span style={{ color: '#00e5ff' }}>{log.event_type}</span>
                    {log.target && <span> | {log.target}</span>}
                  </div>
                  {log.detail && <div style={{ color: '#556677', marginTop: 2 }}>{log.detail}</div>}
                </div>
                <span style={{ color: '#556677', flexShrink: 0, fontSize: 10 }}>
                  {new Date(log.created_at).toLocaleString('zh-CN')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
