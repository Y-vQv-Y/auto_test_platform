import React, { useState, useEffect } from 'react'
import { jenkinsApi } from '../api'
import {
  GitBranch, Plus, Edit3, Trash2, Play,
  CheckCircle, XCircle, Link, Terminal,
} from 'lucide-react'
import toast from 'react-hot-toast'

export default function JenkinsConfig() {
  const [configs, setConfigs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [testingId, setTestingId] = useState(null)
  const [form, setForm] = useState({ name: '', url: '', username: '', api_token: '', job_name: '' })

  useEffect(() => { loadConfigs() }, [])

  async function loadConfigs() {
    try {
      const res = await jenkinsApi.listConfigs()
      setConfigs(res.items || [])
    } catch (err) {
      toast.error('加载 Jenkins 配置失败')
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setEditId(null)
    setForm({ name: '', url: '', username: '', api_token: '', job_name: '' })
    setShowForm(true)
  }

  function openEdit(config) {
    setEditId(config.id)
    setForm({
      name: config.name, url: config.url, username: config.username,
      api_token: '', job_name: config.job_name || '',
    })
    setShowForm(true)
  }

  async function handleSave() {
    if (!form.name.trim() || !form.url.trim()) { toast.error('请填写必要信息'); return }
    try {
      if (editId) {
        await jenkinsApi.updateConfig(editId, form)
        toast.success('配置更新成功')
      } else {
        await jenkinsApi.createConfig(form)
        toast.success('配置创建成功')
      }
      setShowForm(false)
      loadConfigs()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleDelete(id) {
    if (!confirm('确定删除此配置？')) return
    try {
      await jenkinsApi.deleteConfig(id)
      toast.success('配置已删除')
      loadConfigs()
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleTest(id) {
    setTestingId(id)
    try {
      const res = await jenkinsApi.testConnection(id)
      if (res.connected) {
        toast.success(`连接成功! 版本: ${res.version}`)
      } else {
        toast.error(`连接失败: ${res.error}`)
      }
    } catch (err) {
      toast.error(err.message)
    } finally {
      setTestingId(null)
    }
  }

  async function handleTrigger(id) {
    try {
      const res = await jenkinsApi.triggerJob(id)
      if (res.success) {
        toast.success('Job 已触发')
      } else {
        toast.error(`触发失败: ${res.error}`)
      }
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>Jenkins 集成</h1>
          <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>
            在 CI/CD 流水线中自动触发测试，支持 Jenkins Pipeline 集成
          </p>
        </div>
        <button className="cyber-button" style={{ borderColor: '#ff9100', color: '#ff9100' }} onClick={openCreate}>
          <Plus size={16} /> 添加 Jenkins
        </button>
      </div>

      {/* Jenkinsfile 模板 */}
      <div className="cyber-card p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold" style={{ color: '#ff9100' }}>Jenkinsfile 模板</h3>
          <Terminal size={16} style={{ color: '#ff9100' }} />
        </div>
        <p style={{ fontSize: 12, color: '#8899aa', marginBottom: 8 }}>
          将以下代码复制到您项目的 Jenkinsfile 中，即可在 CI/CD 流程中自动触发测试：
        </p>
        <pre style={{
          background: 'rgba(0,0,0,0.3)',
          border: '1px solid rgba(255,145,0,0.1)',
          borderRadius: 8,
          padding: 16,
          fontSize: 12,
          overflow: 'auto',
          maxHeight: 300,
          color: '#e0e8f0',
        }}>
{`stage('AI Auto Test') {
    steps {
        script {
            def response = httpRequest(
                url: "http://localhost:8000/api/v1/jenkins/trigger",
                httpMode: 'POST',
                contentType: 'APPLICATION_JSON',
                requestBody: json(
                    projectName: env.JOB_NAME,
                    deployUrl: 'https://your-deploy-url.com',
                    sourceCodePath: './src',
                    jenkinsJobName: env.JOB_NAME,
                    jenkinsBuildNumber: env.BUILD_NUMBER,
                )
            )
            echo "Test result: \${response}"
        }
    }
}`}
        </pre>
      </div>

      {/* 配置列表 */}
      {loading ? (
        <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
      ) : configs.length === 0 ? (
        <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
          <GitBranch size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
          <p style={{ fontSize: 14 }}>还没有 Jenkins 配置</p>
        </div>
      ) : (
        <div className="space-y-3">
          {configs.map(c => (
            <div key={c.id} className="cyber-card p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(255,145,0,0.1)', border: '1px solid rgba(255,145,0,0.2)' }}>
                    <GitBranch size={20} style={{ color: '#ff9100' }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span style={{ fontSize: 15, fontWeight: 600 }}>{c.name}</span>
                      {c.enabled && <span className="status-badge passed" style={{ fontSize: 10 }}>已启用</span>}
                    </div>
                    <div className="flex items-center gap-2 mt-1" style={{ fontSize: 12, color: '#8899aa' }}>
                      <Link size={12} />
                      <span>{c.url}</span>
                      {c.job_name && <span>| Job: {c.job_name}</span>}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <button className="cyber-button text-xs" onClick={() => handleTest(c.id)} disabled={testingId === c.id}>
                  {testingId === c.id ? '测试中...' : '测试连接'}
                </button>
                <button className="cyber-button primary text-xs" onClick={() => handleTrigger(c.id)}>
                  <Play size={12} /> 触发 Job
                </button>
                <button className="cyber-button text-xs" onClick={() => openEdit(c)}>
                  <Edit3 size={12} /> 编辑
                </button>
                <button className="cyber-button danger text-xs" onClick={() => handleDelete(c.id)}>
                  <Trash2 size={12} /> 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 表单 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-6" style={{ color: '#ff9100' }}>
              {editId ? '编辑 Jenkins 配置' : '添加 Jenkins 配置'}
            </h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>名称 *</label>
                  <input className="cyber-input" placeholder="生产环境 Jenkins"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>Jenkins URL *</label>
                  <input className="cyber-input" placeholder="https://jenkins.example.com"
                    value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>用户名</label>
                  <input className="cyber-input" placeholder="admin"
                    value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>API Token</label>
                  <input className="cyber-input" type="password" placeholder="API Token"
                    value={form.api_token} onChange={(e) => setForm({ ...form, api_token: e.target.value })} />
                </div>
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>Job 名称</label>
                <input className="cyber-input" placeholder="my-app-pipeline"
                  value={form.job_name} onChange={(e) => setForm({ ...form, job_name: e.target.value })} />
              </div>
              <div className="flex gap-3 pt-2">
                <button className="cyber-button flex-1 justify-center" style={{ borderColor: '#ff9100', color: '#ff9100' }}
                  onClick={handleSave}>
                  {editId ? '更新' : '创建'}
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
