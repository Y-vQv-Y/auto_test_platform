import React, { useState, useEffect } from 'react'
import { aiConfigApi } from '../api'
import {
  Plus, Edit3, Trash2, Cpu, Check, Star,
  Globe, Key, Wifi,
} from 'lucide-react'
import toast from 'react-hot-toast'

const providerInfo = {
  openai: { label: 'OpenAI', color: '#00e5ff', placeholder: 'sk-...' },
  anthropic: { label: 'Anthropic Claude', color: '#e040fb', placeholder: 'sk-ant-...' },
  dashscope: { label: '阿里通义千问', color: '#ff9100', placeholder: 'sk-...' },
  deepseek: { label: 'DeepSeek', color: '#448aff', placeholder: 'sk-...' },
  custom: { label: '自定义兼容', color: '#00e676', placeholder: 'API Key' },
}

export default function AIConfig() {
  const [configs, setConfigs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({
    name: '', provider: 'openai', api_key: '', api_base_url: '',
    model: '', temperature: 0.3, max_tokens: 4096, is_default: false,
  })

  useEffect(() => { loadConfigs() }, [])

  async function loadConfigs() {
    try {
      const res = await aiConfigApi.list()
      setConfigs(res.items || [])
    } catch (err) {
      toast.error('加载AI配置失败')
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setEditId(null)
    setForm({ name: '', provider: 'openai', api_key: '', api_base_url: '',
      model: '', temperature: 0.3, max_tokens: 4096, is_default: false })
    setShowForm(true)
  }

  function openEdit(config) {
    setEditId(config.id)
    setForm({
      name: config.name, provider: config.provider, api_key: '',
      api_base_url: config.api_base_url || '', model: config.model || '',
      temperature: config.temperature || 0.3, max_tokens: config.max_tokens || 4096,
      is_default: config.is_default || false,
    })
    setShowForm(true)
  }

  async function handleSave() {
    if (!form.name.trim()) { toast.error('请输入配置名称'); return }
    if (!editId && !form.api_key.trim()) { toast.error('请输入API Key'); return }
    try {
      if (editId) {
        await aiConfigApi.update(editId, form)
        toast.success('配置更新成功')
      } else {
        await aiConfigApi.create(form)
        toast.success('配置创建成功')
      }
      setShowForm(false)
      loadConfigs()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleDelete(id) {
    if (!confirm('确定删除此AI配置？')) return
    try {
      await aiConfigApi.delete(id)
      toast.success('配置已删除')
      loadConfigs()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const [testingId, setTestingId] = useState(null)
  async function handleTestConnection(id) {
    setTestingId(id)
    try {
      const res = await aiConfigApi.testConnection(id)
      toast.success(`连接成功: ${res.response || 'OK'}`)
    } catch (err) {
      toast.error(`连接失败: ${err.message}`)
    } finally {
      setTestingId(null)
    }
  }

  const provider = providerInfo[form.provider] || providerInfo.openai

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>AI 配置</h1>
          <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>
            管理多 AI 接口配置，支持 OpenAI / Claude / 通义千问 / DeepSeek 等
          </p>
        </div>
        <button className="cyber-button" style={{ borderColor: '#e040fb', color: '#e040fb' }} onClick={openCreate}>
          <Plus size={16} /> 添加配置
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
      ) : configs.length === 0 ? (
        <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
          <Cpu size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
          <p style={{ fontSize: 14 }}>还没有 AI 配置，点击上方按钮添加</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {configs.map(c => {
            const info = providerInfo[c.provider] || providerInfo.custom
            return (
              <div key={c.id} className="cyber-card p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ background: `${info.color}15`, border: `1px solid ${info.color}30` }}>
                      <Cpu size={20} style={{ color: info.color }} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span style={{ fontSize: 15, fontWeight: 600 }}>{c.name}</span>
                        {c.is_default && <Star size={14} style={{ color: '#ff9100', fill: '#ff9100' }} />}
                      </div>
                      <span className="status-badge pending" style={{ fontSize: 11 }}>{info.label}</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2 mb-4">
                  <div className="flex items-center gap-2" style={{ fontSize: 12, color: '#8899aa' }}>
                    <Key size={12} />
                    <span>{c.api_key_preview || '未设置'}</span>
                  </div>
                  {c.model && (
                    <div className="flex items-center gap-2" style={{ fontSize: 12, color: '#8899aa' }}>
                      <Globe size={12} />
                      <span>模型: {c.model}</span>
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: '#556677' }}>
                    温度: {c.temperature} | 最大Token: {c.max_tokens}
                  </div>
                </div>

                <div className="flex gap-2">
                  <button className="cyber-button text-xs flex-1 justify-center"
                    onClick={() => handleTestConnection(c.id)} disabled={testingId === c.id}
                    title="测试与AI服务的连通性">
                    <Wifi size={12} /> {testingId === c.id ? '测试中...' : '测试连接'}
                  </button>
                  <button className="cyber-button text-xs flex-1 justify-center" onClick={() => openEdit(c)}>
                    <Edit3 size={12} /> 编辑
                  </button>
                  <button className="cyber-button danger text-xs flex-1 justify-center" onClick={() => handleDelete(c.id)}>
                    <Trash2 size={12} /> 删除
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 表单模态框 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-content" style={{ minWidth: 500 }} onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-6" style={{ color: '#e040fb' }}>
              {editId ? '编辑 AI 配置' : '新增 AI 配置'}
            </h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>配置名称 *</label>
                  <input className="cyber-input" placeholder="My OpenAI Config"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>提供商 *</label>
                  <select className="cyber-select" value={form.provider}
                    onChange={(e) => setForm({ ...form, provider: e.target.value })}>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic Claude</option>
                    <option value="dashscope">阿里通义千问</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="custom">自定义兼容</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>
                  API Key {!editId ? '*' : ''}
                </label>
                <input className="cyber-input" type="password" placeholder={provider.placeholder}
                  value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                {editId && <p style={{ fontSize: 11, color: '#556677', marginTop: 2 }}>留空则不修改</p>}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>API 地址</label>
                  <input className="cyber-input" placeholder="https://api.openai.com/v1"
                    value={form.api_base_url} onChange={(e) => setForm({ ...form, api_base_url: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>模型</label>
                  <input className="cyber-input" placeholder="gpt-4 / claude-3-sonnet"
                    value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>温度</label>
                  <input className="cyber-input" type="number" step="0.1" min="0" max="2"
                    value={form.temperature} onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) || 0 })} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>最大 Token</label>
                  <input className="cyber-input" type="number"
                    value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: parseInt(e.target.value) || 4096 })} />
                </div>
                <div className="flex items-end pb-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={form.is_default}
                      onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                      style={{ accentColor: '#00e5ff' }} />
                    <span style={{ fontSize: 12, color: '#8899aa' }}>设为默认</span>
                  </label>
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button className="cyber-button flex-1 justify-center" style={{ borderColor: '#e040fb', color: '#e040fb' }}
                  onClick={handleSave}>
                  <Check size={14} /> {editId ? '更新配置' : '创建配置'}
                </button>
                <button className="cyber-button flex-1 justify-center" style={{ color: '#8899aa' }}
                  onClick={() => setShowForm(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
