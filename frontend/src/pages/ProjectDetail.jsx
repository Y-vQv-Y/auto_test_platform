import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { projectApi, testRunApi, testCaseApi, aiConfigApi, captchaApi } from '../api'
import {
  Play, Cpu, RefreshCw, Plus, Trash2, Eye,
  ArrowLeft, Code, Globe, Smartphone, Shield,
  CheckCircle, XCircle, Clock, Bot,
  FileText, Edit3, Download, Upload,
} from 'lucide-react'
import toast from 'react-hot-toast'

export default function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [testRuns, setTestRuns] = useState([])
  const [testCases, setTestCases] = useState([])
  const [aiConfigs, setAiConfigs] = useState([])
  const [loginStatus, setLoginStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedCases, setSelectedCases] = useState([])
  const [runStatus, setRunStatus] = useState(null) // {runId, ws}
  const wsRef = useRef(null)

  // 生成测试配置
  const [genConfig, setGenConfig] = useState({ ai_config_id: '', test_type: '功能测试' })
  const [showGenModal, setShowGenModal] = useState(false)
  const [generating, setGenerating] = useState(false)

  // 编辑项目
  const [showEditModal, setShowEditModal] = useState(false)
  const [editForm, setEditForm] = useState({})

  // 用例代码编辑
  const [editCase, setEditCase] = useState(null) // { id, name, code }
  const [editCaseCode, setEditCaseCode] = useState('')
  const [savingCase, setSavingCase] = useState(false)

  // 源码上传
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    loadData()
    return () => { if (wsRef.current) wsRef.current.close() }
  }, [id])

  async function loadData() {
    try {
      const [p, runs, cases, configs] = await Promise.all([
        projectApi.get(id),
        testRunApi.list({ project_id: id, page_size: 50 }),
        testCaseApi.list({ project_id: id }),
        aiConfigApi.list(),
      ])
      setProject(p)
      setTestRuns(runs.items || [])
      setTestCases(cases.items || [])
      setAiConfigs(configs.items || [])
      // 获取登录状态
      try {
        const login = await captchaApi.status(id)
        setLoginStatus(login)
      } catch (e) { /* ignore */ }
    } catch (err) {
      toast.error('加载项目数据失败')
    } finally {
      setLoading(false)
    }
  }

  // 打开编辑模态框
  function openEditModal() {
    setEditForm({
      name: project.name || '',
      description: project.description || '',
      deploy_url: project.deploy_url || '',
      source_code_path: project.source_code_path || '',
      framework_type: project.framework_type || '',
      repo_url: project.repo_url || '',
      repo_branch: project.repo_branch || 'main',
    })
    setShowEditModal(true)
  }

  // 保存编辑
  async function handleEditSave() {
    if (!editForm.name.trim()) { toast.error('项目名称不能为空'); return }
    try {
      await projectApi.update(id, editForm)
      toast.success('项目更新成功')
      setShowEditModal(false)
      loadData()
    } catch (err) {
      toast.error(err.message)
    }
  }

  // 上传源代码
  async function handleUploadSource(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await projectApi.uploadSource(id, file)
      toast.success(res.message || '源码上传成功')
      loadData()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  // 创建测试运行（有测试用例时自动执行）
  async function handleCreateRun() {
    try {
      const run = await testRunApi.create(id, `手动运行 ${new Date().toLocaleString('zh-CN')}`)
      if (testCases.length > 0) {
        toast.success('测试运行已创建，正在自动执行...')
        navigate(`/test-runs?id=${run.id}`)
        // 后台自动触发执行
        try {
          await testRunApi.execute(run.id, {
            test_case_ids: testCases.map(c => c.id),
            deploy_url: project.deploy_url,
            use_login: true,
            readonly_mode: true,
          })
        } catch (e) { /* 执行结果在 TestRunView 页面显示 */ }
      } else {
        toast.success('测试运行已创建（暂无测试用例，请先 AI 生成）')
        navigate(`/test-runs?id=${run.id}`)
      }
    } catch (err) {
      toast.error(err.message)
    }
  }

  // AI 生成测试用例
  async function handleGenerate() {
    if (!genConfig.ai_config_id) { toast.error('请选择AI配置'); return }
    setGenerating(true)
    try {
      // 先创建运行
      const run = await testRunApi.create(id, `AI生成 - ${genConfig.test_type}`)
      // 生成测试用例
      await testRunApi.generate(run.id, {
        ai_config_id: parseInt(genConfig.ai_config_id),
        test_type: genConfig.test_type,
        source_code_path: project.source_code_path,
      })
      toast.success('AI 生成已启动，将在后台执行...')
      setShowGenModal(false)
      loadData()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setGenerating(false)
    }
  }

  // 执行测试
  async function handleRunTest() {
    if (selectedCases.length === 0) { toast.error('请选择至少一个测试用例'); return }
    try {
      // 创建并执行测试运行
      const cases = testCases.filter(c => selectedCases.includes(c.id))
      if (cases.length === 0) { toast.error('所选测试用例无效'); return }

      const run = await testRunApi.create(id, `执行测试 ${new Date().toLocaleString('zh-CN')}`)

      // 连接 WebSocket
      const ws = testRunApi.connectWs(run.id)
      wsRef.current = ws
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        setRunStatus(prev => ({ ...prev, progress: data }))
      }

      setRunStatus({ runId: run.id, progress: null, ws })
      setActiveTab('runs')

      setTimeout(async () => {
        try {
          await testRunApi.execute(run.id, {
            test_case_ids: selectedCases,
            deploy_url: project.deploy_url,
            use_login: true,
            readonly_mode: true,
          })
          toast.success('测试执行完成')
          loadData()
        } catch (err) {
          toast.error(err.message)
        } finally {
          setRunStatus(null)
        }
      }, 500)
    } catch (err) {
      toast.error(err.message)
    }
  }

  // 验证码登录 / 手动粘贴 Cookie
  const [showCookieModal, setShowCookieModal] = useState(false)
  const [loginUrl, setLoginUrl] = useState('')
  const [cookieInput, setCookieInput] = useState('')

  async function handleCaptchaLogin() {
    try {
      const res = await captchaApi.login(id)
      if (res.manual_mode) {
        // Docker 模式：显示 URL 和粘贴 Cookie 界面
        setLoginUrl(res.login_url || project.deploy_url || '')
        setCookieInput('')
        setShowCookieModal(true)
      } else {
        toast.success('登录成功')
        loadData()
      }
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleSaveCookies() {
    if (!cookieInput.trim()) { toast.error('请粘贴 Cookie'); return }
    try {
      await captchaApi.saveCookies(id, cookieInput.trim())
      toast.success('Cookie 保存成功')
      setShowCookieModal(false)
      loadData()
    } catch (err) {
      toast.error(err.message)
    }
  }

  const [checkingSession, setCheckingSession] = useState(false)
  async function handleCheckSession() {
    setCheckingSession(true)
    try {
      const res = await captchaApi.checkSession(id)
      if (res.session_valid) {
        toast.success('登录态有效')
      } else {
        toast.error('登录态已失效，请重新登录')
      }
      loadData()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setCheckingSession(false)
    }
  }

  async function handleRefreshLogin() {
    try {
      const res = await captchaApi.refreshLogin(id)
      if (res.has_login) {
        toast.success('重新登录成功')
        loadData()
      } else {
        toast.error('重新登录失败')
      }
    } catch (err) {
      toast.error(err.message)
    }
  }

  async function handleDeleteCase(caseId) {
    try {
      await testCaseApi.delete(caseId)
      toast.success('测试用例已删除')
      loadData()
    } catch (err) {
      toast.error(err.message)
    }
  }

  function toggleCase(caseId) {
    setSelectedCases(prev =>
      prev.includes(caseId) ? prev.filter(c => c !== caseId) : [...prev, caseId]
    )
  }

  if (loading) {
    return <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
  }
  if (!project) {
    return <div className="text-center py-16" style={{ color: '#ff1744' }}>项目不存在</div>
  }

  const tabs = [
    { key: 'overview', label: '概览', icon: Eye },
    { key: 'cases', label: `测试用例 (${testCases.length})`, icon: Code },
    { key: 'runs', label: `运行记录 (${testRuns.length})`, icon: Play },
  ]

  return (
    <div className="animate-fade-in space-y-6">
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <button
            className="flex items-center gap-1 mb-3 transition-all"
            style={{ color: '#556677', fontSize: 12 }}
            onClick={() => navigate('/projects')}
            onMouseEnter={(e) => e.currentTarget.style.color = '#00e5ff'}
            onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
          >
            <ArrowLeft size={14} /> 返回项目列表
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold" style={{ color: '#e0e8f0' }}>{project.name}</h1>
            <button
              className="p-2 rounded-lg transition-all"
              style={{ color: '#556677' }}
              onClick={openEditModal}
              onMouseEnter={(e) => e.currentTarget.style.color = '#00e5ff'}
              onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
              title="编辑项目"
            >
              <Edit3 size={16} />
            </button>
          </div>
          {project.description && (
            <p style={{ color: '#8899aa', fontSize: 13, marginTop: 4 }}>{project.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button className="cyber-button" onClick={() => setShowGenModal(true)} disabled={generating}>
            <Bot size={16} /> {generating ? '生成中...' : 'AI 生成测试'}
          </button>
          <button className="cyber-button primary" onClick={handleRunTest} disabled={selectedCases.length === 0}>
            <Play size={16} /> 执行测试 ({selectedCases.length})
          </button>
          <button className="cyber-button" onClick={handleCreateRun}>
            <Plus size={16} /> 新建运行
          </button>
        </div>
      </div>

      {/* 项目信息 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="cyber-card p-4 flex items-center gap-3">
          <Globe size={20} style={{ color: '#448aff' }} />
          <div>
            <div style={{ fontSize: 11, color: '#8899aa' }}>部署 URL</div>
            <div style={{ fontSize: 13 }}>{project.deploy_url || '未配置'}</div>
          </div>
        </div>
        <div className="cyber-card p-4 flex items-center gap-3">
          <Code size={20} style={{ color: '#e040fb' }} />
          <div className="flex-1 min-w-0">
            <div style={{ fontSize: 11, color: '#8899aa' }}>源代码路径</div>
            <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {project.source_code_path || '未配置'}
            </div>
          </div>
          <input type="file" accept=".zip" ref={fileInputRef} style={{ display: 'none' }}
            onChange={handleUploadSource} />
          <button className="cyber-button" style={{ fontSize: 12, flexShrink: 0 }}
            onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            <Upload size={14} /> {uploading ? '上传中...' : '上传 Zip'}
          </button>
        </div>
        <div className="cyber-card p-4 flex items-center gap-3">
          <Shield size={20} style={{ color: loginStatus?.has_login ? (loginStatus?.session_valid ? '#00e676' : '#ff1744') : '#ff9100' }} />
          <div className="flex-1">
            <div style={{ fontSize: 11, color: '#8899aa' }}>登录状态</div>
            <div style={{ fontSize: 13, color: loginStatus?.has_login ? (loginStatus?.session_valid ? '#00e676' : '#ff1744') : '#ff9100' }}>
              {loginStatus?.has_login 
                ? (loginStatus?.session_valid ? '已登录 (有效)' : '已登录 (失效)') 
                : '未登录'}
            </div>
          </div>
          <div className="flex gap-1">
            <button 
              className="p-1.5 rounded hover:bg-white/5 transition-all" 
              style={{ color: '#00e5ff' }}
              onClick={handleCheckSession}
              disabled={checkingSession || !loginStatus?.has_login}
              title="校验登录态"
            >
              <RefreshCw size={14} className={checkingSession ? 'animate-spin' : ''} />
            </button>
            <button 
              className="p-1.5 rounded hover:bg-white/5 transition-all" 
              style={{ color: '#ff9100' }}
              onClick={handleCaptchaLogin}
              title="重新登录"
            >
              <Smartphone size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* 标签页 */}
      <div className="flex gap-1 border-b" style={{ borderColor: 'rgba(0,229,255,0.08)' }}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            className="flex items-center gap-2 px-4 py-3 text-sm transition-all border-b-2"
            style={{
              color: activeTab === tab.key ? '#00e5ff' : '#8899aa',
              borderColor: activeTab === tab.key ? '#00e5ff' : 'transparent',
            }}
            onClick={() => setActiveTab(tab.key)}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* 概览 Tab */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="cyber-card p-5">
            <h3 className="text-sm font-semibold mb-4" style={{ color: '#00e5ff' }}>项目统计</h3>
            <div className="grid grid-cols-2 gap-4">
              {[
                { label: '测试用例', value: testCases.length, color: '#e040fb' },
                { label: '运行次数', value: testRuns.length, color: '#00e5ff' },
                { label: '通过次数', value: testRuns.filter(r => r.status === 'passed').length, color: '#00e676' },
                { label: '失败次数', value: testRuns.filter(r => r.status === 'failed').length, color: '#ff1744' },
              ].map((s, i) => (
                <div key={i} className="text-center p-4 rounded-lg" style={{ background: 'rgba(0,0,0,0.2)' }}>
                  <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</div>
                  <div style={{ fontSize: 12, color: '#8899aa', marginTop: 4 }}>{s.label}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="cyber-card p-5">
            <h3 className="text-sm font-semibold mb-4" style={{ color: '#00e5ff' }}>快速操作</h3>
            <div className="space-y-3">
              <button className="w-full cyber-card p-3 flex items-center gap-3 transition-all hover:border-cyan-500/30"
                onClick={() => { setGenConfig({ ...genConfig, ai_config_id: aiConfigs.find(c => c.is_default)?.id || '' }); setShowGenModal(true) }}>
                <Bot size={18} style={{ color: '#e040fb' }} />
                <div className="text-left">
                  <div style={{ fontSize: 13 }}>AI 生成测试用例</div>
                  <div style={{ fontSize: 11, color: '#8899aa' }}>读取源代码自动生成</div>
                </div>
              </button>
              <button className="w-full cyber-card p-3 flex items-center gap-3 transition-all hover:border-cyan-500/30"
                onClick={handleCaptchaLogin}>
                <Smartphone size={18} style={{ color: '#ff9100' }} />
                <div className="text-left">
                  <div style={{ fontSize: 13 }}>处理验证码登录</div>
                  <div style={{ fontSize: 11, color: '#8899aa' }}>弹出浏览器完成滑块验证</div>
                </div>
              </button>
              <button className="w-full cyber-card p-3 flex items-center gap-3 transition-all hover:border-cyan-500/30"
                onClick={handleCreateRun}>
                <Play size={18} style={{ color: '#00e676' }} />
                <div className="text-left">
                  <div style={{ fontSize: 13 }}>手动触发测试</div>
                  <div style={{ fontSize: 11, color: '#8899aa' }}>{testCases.length > 0 ? `执行全部 ${testCases.length} 个用例` : '创建空运行（暂无用例）'}</div>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 测试用例 Tab */}
      {activeTab === 'cases' && (
        <div className="space-y-3">
          {/* 操作栏 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  style={{ accentColor: '#00e5ff' }}
                  checked={testCases.length > 0 && selectedCases.length === testCases.length}
                  ref={el => {
                    if (el) el.indeterminate = selectedCases.length > 0 && selectedCases.length < testCases.length
                  }}
                  onChange={() => {
                    if (selectedCases.length === testCases.length) {
                      setSelectedCases([])
                    } else {
                      setSelectedCases(testCases.map(c => c.id))
                    }
                  }}
                />
                <span style={{ fontSize: 13, color: '#8899aa' }}>
                  {selectedCases.length > 0
                    ? `已选 ${selectedCases.length} / ${testCases.length}`
                    : '全选'}
                </span>
              </label>
              {selectedCases.length > 0 && (
                <button
                  className="cyber-button danger"
                  style={{ fontSize: 12 }}
                  onClick={async () => {
                    if (!confirm(`确定删除选中的 ${selectedCases.length} 个测试用例？`)) return
                    try {
                      await Promise.all(selectedCases.map(id => testCaseApi.delete(id)))
                      toast.success(`已删除 ${selectedCases.length} 个测试用例`)
                      setSelectedCases([])
                      loadData()
                    } catch (err) {
                      toast.error(err.message)
                    }
                  }}
                >
                  <Trash2 size={14} /> 删除选中
                </button>
              )}
            </div>
            {testCases.length > 0 && (
              <button
                className="cyber-button"
                style={{ fontSize: 12 }}
                onClick={() => window.open(testCaseApi.exportExcelUrl(id), '_blank')}
              >
                <Download size={14} /> 导出 Excel
              </button>
            )}
          </div>
      
          {testCases.length === 0 ? (
            <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
              <Bot size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
              <p style={{ fontSize: 14 }}>还没有测试用例，点击「AI 生成测试」创建</p>
            </div>
          ) : (
            testCases.map((tc) => (
              <div key={tc.id} className="cyber-card p-4 flex items-center gap-4 transition-all hover:border-cyan-500/30">
                <input
                  type="checkbox"
                  checked={selectedCases.includes(tc.id)}
                  onChange={() => toggleCase(tc.id)}
                  className="w-4 h-4 rounded flex-shrink-0"
                  style={{ accentColor: '#00e5ff' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      style={{ fontSize: 14, fontWeight: 500, cursor: 'pointer', color: '#00e5ff' }}
                      onClick={() => {
                        testCaseApi.getCode(tc.id).then(res => {
                          setEditCase(tc)
                          setEditCaseCode(res.code || '')
                        })
                      }}
                    >{tc.name}</span>
                    {tc.priority === 'high' && (
                      <span className="status-badge failed" style={{ fontSize: 10 }}>高优</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="status-badge pending" style={{ fontSize: 10 }}>{tc.category || '功能测试'}</span>
                    <span style={{ fontSize: 11, color: '#556677' }}>
                      {new Date(tc.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                </div>
                <button
                  className="p-2 rounded-lg transition-all flex-shrink-0"
                  style={{ color: '#556677' }}
                  onClick={() => handleDeleteCase(tc.id)}
                  onMouseEnter={(e) => e.currentTarget.style.color = '#ff1744'}
                  onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* 用例代码编辑模态框 */}
      {editCase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setEditCase(null)}>
          <div className="cyber-card p-6 w-full max-w-3xl max-h-[85vh] flex flex-col"
            style={{ borderColor: '#00e5ff44' }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold" style={{ color: '#00e5ff' }}>
                <Edit3 size={16} className="inline mr-2" />编辑用例 — {editCase.name}
              </h3>
              <button className="p-1 rounded hover:bg-white/5" onClick={() => setEditCase(null)}>✕</button>
            </div>
            <textarea className="w-full flex-1 p-4 rounded-lg font-mono text-sm"
              style={{ minHeight: 300, background: '#0a1628', color: '#e0e0e0', border: '1px solid #334466', resize: 'vertical', lineHeight: 1.6 }}
              value={editCaseCode} onChange={e => setEditCaseCode(e.target.value)} spellCheck={false} />
            <div className="flex items-center justify-end gap-3 mt-4">
              <button className="px-4 py-2 rounded-lg text-sm" style={{ background: '#1a2744', color: '#8899aa' }}
                onClick={() => setEditCase(null)}>取消</button>
              <button className="px-4 py-2 rounded-lg text-sm font-medium cyber-button" disabled={savingCase}
                onClick={async () => {
                  setSavingCase(true)
                  try {
                    await testCaseApi.update(editCase.id, { code: editCaseCode })
                    toast.success('用例已更新')
                    setEditCase(null)
                    loadData()
                  } catch (err) { toast.error(err.message || '保存失败') }
                  finally { setSavingCase(false) }
                }}>{savingCase ? '保存中…' : '保存'}</button>
            </div>
          </div>
        </div>
      )}

      {/* 运行记录 Tab */}
      {activeTab === 'runs' && (
        <div className="space-y-3">
          {testRuns.length === 0 ? (
            <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
              <Clock size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
              <p style={{ fontSize: 14 }}>还没有测试运行记录</p>
            </div>
          ) : (
            testRuns.map((run) => (
              <div
                key={run.id}
                className="cyber-card p-4 flex items-center justify-between cursor-pointer transition-all hover:border-cyan-500/30"
                onClick={() => navigate(`/test-runs?id=${run.id}`)}
              >
                <div className="flex items-center gap-3">
                  {run.status === 'passed' ? <CheckCircle size={20} style={{ color: '#00e676' }} /> :
                   run.status === 'failed' ? <XCircle size={20} style={{ color: '#ff1744' }} /> :
                   run.status === 'running' ? <RefreshCw size={20} style={{ color: '#00e5ff' }} /> :
                   <Clock size={20} style={{ color: '#8899aa' }} />}
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{run.name}</div>
                    <div style={{ fontSize: 11, color: '#556677' }}>
                      {new Date(run.created_at).toLocaleString('zh-CN')} | {run.trigger_mode}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div style={{ fontSize: 12, color: '#8899aa' }}>
                      {run.passed_cases || 0}/{run.total_cases || 0} 通过
                    </div>
                    {run.duration_seconds > 0 && (
                      <div style={{ fontSize: 11, color: '#556677' }}>{run.duration_seconds.toFixed(1)}s</div>
                    )}
                  </div>
                  <span className={`status-badge ${run.status}`}>{run.status}</span>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 编辑项目模态框 */}
      {showEditModal && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-6" style={{ color: '#00e5ff' }}>编辑项目</h2>
            <div className="space-y-4">
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>项目名称 *</label>
                <input className="cyber-input" value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>项目描述</label>
                <textarea className="cyber-input" rows={2} value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>部署 URL</label>
                <input className="cyber-input" value={editForm.deploy_url}
                  onChange={(e) => setEditForm({ ...editForm, deploy_url: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>源代码路径</label>
                <input className="cyber-input" value={editForm.source_code_path}
                  onChange={(e) => setEditForm({ ...editForm, source_code_path: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>框架类型</label>
                <input className="cyber-input" placeholder="如: Vue / React / Django" value={editForm.framework_type}
                  onChange={(e) => setEditForm({ ...editForm, framework_type: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>仓库地址</label>
                <input className="cyber-input" value={editForm.repo_url}
                  onChange={(e) => setEditForm({ ...editForm, repo_url: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>分支</label>
                <input className="cyber-input" value={editForm.repo_branch}
                  onChange={(e) => setEditForm({ ...editForm, repo_branch: e.target.value })} />
              </div>
              <div className="flex gap-3 pt-2">
                <button className="cyber-button flex-1 justify-center" onClick={handleEditSave}>保存修改</button>
                <button className="cyber-button flex-1 justify-center" style={{ color: '#8899aa' }}
                  onClick={() => setShowEditModal(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 粘贴 Cookie 模态框 */}
      {showCookieModal && (
        <div className="modal-overlay" onClick={() => setShowCookieModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4" style={{ color: '#ff9100' }}>手动保存登录态</h2>
            <p style={{ fontSize: 13, color: '#8899aa', marginBottom: 12 }}>
              在 <strong>你自己的浏览器</strong> 中打开以下地址完成登录，然后按 <strong>F12 → Console</strong> 执行命令复制 Cookie：
            </p>
            <div className="cyber-card p-3 mb-4 flex items-center justify-between">
              <code style={{ fontSize: 13, color: '#00e5ff', wordBreak: 'break-all' }}>{loginUrl}</code>
              <button className="cyber-button" style={{ fontSize: 11, flexShrink: 0 }}
                onClick={() => { navigator.clipboard?.writeText(loginUrl); toast.success('已复制 URL') }}>
                复制
              </button>
            </div>
            <div className="cyber-card p-3 mb-3" style={{ background: 'rgba(0,0,0,0.3)' }}>
              <div style={{ fontSize: 11, color: '#556677', marginBottom: 6 }}>Console 中执行以下命令：</div>
              <pre style={{ fontSize: 11, color: '#e0e8f0', userSelect: 'all' }}>
{`copy(JSON.stringify(document.cookie.split('; ').map(c => {
  const [n,...v] = c.split('=');
  return {name:n,value:v.join('='),domain:location.hostname,path:'/'};
})));`}
              </pre>
            </div>
            <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>粘贴 Cookie（JSON 数组）：</label>
            <textarea className="cyber-input" rows={5} placeholder='[{"name":"token","value":"xxx","domain":".example.com","path":"/"}]'
              value={cookieInput} onChange={(e) => setCookieInput(e.target.value)} />
            <div className="flex gap-3 pt-3">
              <button className="cyber-button flex-1 justify-center" style={{ borderColor: '#ff9100', color: '#ff9100' }}
                onClick={handleSaveCookies}>保存 Cookie</button>
              <button className="cyber-button flex-1 justify-center" style={{ color: '#8899aa' }}
                onClick={() => setShowCookieModal(false)}>取消</button>
            </div>
          </div>
        </div>
      )}

      {/* AI 生成模态框 */}
      {showGenModal && (
        <div className="modal-overlay" onClick={() => setShowGenModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-6" style={{ color: '#e040fb' }}>AI 生成测试用例</h2>
            <div className="space-y-4">
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>AI 配置</label>
                <select className="cyber-select" value={genConfig.ai_config_id}
                  onChange={(e) => setGenConfig({ ...genConfig, ai_config_id: e.target.value })}>
                  <option value="">请选择 AI 配置</option>
                  {aiConfigs.filter(c => c.status === 'active').map(c => (
                    <option key={c.id} value={c.id}>{c.name} ({c.provider})</option>
                  ))}
                </select>
                {aiConfigs.length === 0 && (
                  <p style={{ fontSize: 11, color: '#ff9100', marginTop: 4 }}>
                    暂无AI配置，请先前往 AI 配置页面添加
                  </p>
                )}
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>测试类型</label>
                <select className="cyber-select" value={genConfig.test_type}
                  onChange={(e) => setGenConfig({ ...genConfig, test_type: e.target.value })}>
                  <option value="功能测试">功能测试</option>
                  <option value="冒烟测试">冒烟测试</option>
                  <option value="回归测试">回归测试</option>
                  <option value="安全测试">安全测试</option>
                  <option value="性能测试">性能测试</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#8899aa', marginBottom: 6, display: 'block' }}>源代码路径</label>
                <input className="cyber-input" value={project.source_code_path} disabled
                  placeholder="请在项目设置中配置" />
              </div>
              <div className="flex gap-3 pt-2">
                <button className="cyber-button flex-1 justify-center" style={{ borderColor: '#e040fb', color: '#e040fb' }}
                  onClick={handleGenerate} disabled={generating || !genConfig.ai_config_id}>
                  {generating ? '正在生成...' : '开始生成'}
                </button>
                <button className="cyber-button flex-1 justify-center" style={{ color: '#8899aa' }}
                  onClick={() => setShowGenModal(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
