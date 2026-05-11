import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projectApi } from '../api'
import {
  Plus, Edit3, Trash2, ExternalLink, Code,
  Globe, Folder, Search,
} from 'lucide-react'
import toast from 'react-hot-toast'

export default function Projects() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState('')
  const [form, setForm] = useState({ name: '', description: '', source_code_path: '', deploy_url: '' })
  const navigate = useNavigate()

  useEffect(() => { loadProjects() }, [])

  async function loadProjects() {
    try {
      const res = await projectApi.list({ page_size: 100 })
      setProjects(res.items || [])
    } catch (err) {
      toast.error('加载项目列表失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate() {
    if (!form.name.trim()) { toast.error('请输入项目名称'); return }
    try {
      await projectApi.create(form)
      toast.success('项目创建成功')
      setShowCreate(false)
      setForm({ name: '', description: '', source_code_path: '', deploy_url: '' })
      loadProjects()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleDelete(id) {
    if (!confirm('确定删除此项目？所有相关数据将被删除。')) return
    try {
      await projectApi.delete(id)
      toast.success('项目已删除')
      loadProjects()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const filtered = projects.filter(p =>
    !search || p.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>项目管理</h1>
          <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>
            管理被测试项目及其源代码、部署配置
          </p>
        </div>
        <button className="cyber-button" onClick={() => setShowCreate(true)}>
          <Plus size={16} /> 新建项目
        </button>
      </div>

      {/* 搜索 */}
      <div className="flex items-center w-72 cyber-input" style={{ padding: '4px 14px' }}>
        <Search size={16} style={{ color: '#556677', flexShrink: 0 }} />
        <input
          className="bg-transparent border-none outline-none flex-1"
          style={{ color: '#e0e8f0', fontSize: 14, paddingLeft: 8 }}
          placeholder="搜索项目..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* 项目列表 */}
      {loading ? (
        <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
      ) : filtered.length === 0 ? (
        <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
          <Folder size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
          <p style={{ fontSize: 14 }}>{search ? '没有找到匹配的项目' : '还没有项目，点击上方按钮创建'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((p) => (
            <div
              key={p.id}
              className="cyber-card p-5 cursor-pointer transition-all hover:translate-y-[-2px]"
              onClick={() => navigate(`/projects/${p.id}`)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Folder size={18} style={{ color: '#448aff' }} />
                  <h3 className="font-semibold" style={{ fontSize: 15 }}>{p.name}</h3>
                </div>
                <div className="flex gap-1">
                  <button
                    className="p-1.5 rounded transition-all"
                    style={{ color: '#556677' }}
                    onClick={(e) => { e.stopPropagation(); handleDelete(p.id) }}
                    onMouseEnter={(e) => e.currentTarget.style.color = '#ff1744'}
                    onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              {p.description && (
                <p style={{ fontSize: 12, color: '#8899aa', marginBottom: 12, lineHeight: 1.5 }}>
                  {p.description.length > 80 ? p.description.slice(0, 80) + '...' : p.description}
                </p>
              )}

              <div className="space-y-1.5">
                {p.deploy_url && (
                  <div className="flex items-center gap-2" style={{ fontSize: 12, color: '#556677' }}>
                    <Globe size={12} />
                    <span className="truncate">{p.deploy_url}</span>
                  </div>
                )}
                {p.source_code_path && (
                  <div className="flex items-center gap-2" style={{ fontSize: 12, color: '#556677' }}>
                    <Code size={12} />
                    <span className="truncate">{p.source_code_path}</span>
                  </div>
                )}
                {p.framework_type && (
                  <span className="status-badge pending" style={{ fontSize: 11 }}>
                    {p.framework_type}
                  </span>
                )}
              </div>

              <div style={{ fontSize: 11, color: '#556677', marginTop: 12 }}>
                创建于 {new Date(p.created_at).toLocaleDateString('zh-CN')}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 创建模态框 */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-6" style={{ color: '#00e5ff' }}>新建项目</h2>
            <div className="space-y-4">
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>项目名称 *</label>
                <input className="cyber-input" placeholder="输入项目名称" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>项目描述</label>
                <textarea className="cyber-input" rows={2} placeholder="项目描述" value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>部署 URL</label>
                <input className="cyber-input" placeholder="https://example.com" value={form.deploy_url}
                  onChange={(e) => setForm({ ...form, deploy_url: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>源代码路径</label>
                <input className="cyber-input" placeholder="/path/to/source/code" value={form.source_code_path}
                  onChange={(e) => setForm({ ...form, source_code_path: e.target.value })} />
              </div>
              <div className="flex gap-3 pt-2">
                <button className="cyber-button flex-1 justify-center" onClick={handleCreate}>创建项目</button>
                <button className="cyber-button flex-1 justify-center" style={{ color: '#8899aa' }}
                  onClick={() => setShowCreate(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
