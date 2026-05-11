import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { testRunApi } from '../api'
import useWebSocket from '../hooks/useWebSocket'
import {
  RefreshCw, Download, Terminal, Camera,
  ChevronDown, ChevronRight, CheckCircle, XCircle,
  Clock, AlertTriangle, FileText, ExternalLink, Trash2,
  Search, ChevronLeft,
} from 'lucide-react'
import toast from 'react-hot-toast'

export default function TestRunView() {
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('id')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedResults, setExpandedResults] = useState(new Set())
  const handleWsMessage = useCallback((msg) => {
    if (msg.type === 'progress') {
      setData(prev => prev ? { ...prev, progress: msg } : prev)
    } else if (msg.type === 'generate_complete' || msg.type === 'generate_error') {
      // Refresh full data when generation completes or fails
      if (runId) loadRun(runId, true)
    }
  }, [runId])

  const { status: wsStatus } = useWebSocket(
    runId ? () => testRunApi.connectWs(runId) : null,
    { onMessage: handleWsMessage, maxRetries: Infinity }
  )

  useEffect(() => {
    if (runId) {
      loadRun(runId)
    } else {
      setLoading(false)
    }
    // Polling only when WebSocket is NOT connected — no race condition
    const pollTimer = setInterval(() => {
      if (runId && wsStatus !== 'connected') {
        loadRun(runId, true)
      }
    }, 5000)
    return () => clearInterval(pollTimer)
  }, [runId, wsStatus])

  async function loadRun(id, silent = false) {
    if (!silent) setLoading(true)
    try {
      const res = await testRunApi.get(id)
      setData(res)
    } catch (err) {
      if (!silent) toast.error('加载测试运行数据失败')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // 没有指定ID时，显示运行列表
  if (!runId) {
    return <TestRunList />
  }

  if (loading) {
    return <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
  }
  if (!data) {
    return <div className="text-center py-16" style={{ color: '#ff1744' }}>测试运行不存在</div>
  }

  const { run, results, progress } = data
  const passedCount = results?.filter(r => r.status === 'passed').length || 0
  const failedCount = results?.filter(r => r.status === 'failed').length || 0
  const errorCount = results?.filter(r => r.status === 'error').length || 0

  function toggleResult(id) {
    setExpandedResults(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="animate-fade-in space-y-6">
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>
            {run.name || `测试运行 #${run.id}`}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`status-badge ${run.status}`}>
              {run.status === 'passed' ? <CheckCircle size={12} /> :
               run.status === 'failed' ? <XCircle size={12} /> :
               run.status === 'running' ? <RefreshCw size={12} /> : <Clock size={12} />}
              {run.status}
            </span>
            <span style={{ fontSize: 12, color: '#8899aa' }}>
              项目ID: {run.project_id} | 触发: {run.trigger_mode}
            </span>
            {run.duration_seconds > 0 && (
              <span style={{ fontSize: 12, color: '#8899aa' }}>
                耗时: {run.duration_seconds.toFixed(1)}s
              </span>
            )}
            <span className="flex items-center gap-1" style={{ fontSize: 11, color: wsStatus === 'connected' ? '#00e676' : wsStatus === 'reconnecting' ? '#ff9100' : '#ff5252' }}>
              <span className={`w-1.5 h-1.5 rounded-full ${wsStatus === 'reconnecting' ? 'animate-pulse' : ''}`} style={{
                background: wsStatus === 'connected' ? '#00e676' : wsStatus === 'reconnecting' ? '#ff9100' : '#ff5252',
              }} />
              {wsStatus === 'connected' ? '实时' : wsStatus === 'reconnecting' ? '重连中' : '离线'}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="cyber-button" onClick={() => window.open(testRunApi.getReportHtmlUrl(runId), '_blank')}>
            <FileText size={14} /> 查看报告
          </button>
          <button className="cyber-button" onClick={() => window.open(testRunApi.exportReportUrl(runId), '_blank')}>
            <Download size={14} /> 导出报告
          </button>
          <button className="cyber-button" onClick={() => window.open(testRunApi.exportExcelUrl(runId), '_blank')}>
            <FileText size={14} /> 导出 Excel
          </button>
          <button className="cyber-button" onClick={() => loadRun(runId)}>
            <RefreshCw size={14} /> 刷新
          </button>
          {run.status !== 'running' && (
            <button className="cyber-button danger" onClick={async () => {
              if (!confirm('确定删除此测试运行记录？')) return
              try {
                await testRunApi.delete(runId)
                toast.success('测试运行已删除')
                window.location.href = '/test-runs'
              } catch (err) {
                toast.error(err.message)
              }
            }}>
              <Trash2 size={14} /> 删除
            </button>
          )}
        </div>
      </div>

      {/* 进度 */}
      {progress && (
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between mb-2">
            <span style={{ fontSize: 13, color: '#00e5ff' }}>{progress.message}</span>
            <span style={{ fontSize: 12, color: '#8899aa' }}>{progress.progress}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${progress.progress}%` }} />
          </div>
        </div>
      )}

      {/* 统计 */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: '总用例', value: results?.length || 0, color: '#448aff' },
          { label: '通过', value: passedCount, color: '#00e676' },
          { label: '失败', value: failedCount, color: '#ff1744' },
          { label: '错误', value: errorCount, color: '#ff9100' },
        ].map((s, i) => (
          <div key={i} className="cyber-card p-4 text-center">
            <div className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 12, color: '#8899aa', marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* 结果列表 */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold" style={{ color: '#00e5ff' }}>测试结果明细</h3>
        {(!results || results.length === 0) ? (
          <div className="cyber-card p-8 text-center" style={{ color: '#556677' }}>
            <Terminal size={32} className="mx-auto mb-2" style={{ opacity: 0.3 }} />
            <p style={{ fontSize: 13 }}>暂无测试结果</p>
          </div>
        ) : (
          results.map((result) => (
            <div key={result.id} className="cyber-card overflow-hidden">
              <div
                className="flex items-center justify-between p-4 cursor-pointer transition-all"
                onClick={() => toggleResult(result.id)}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,229,255,0.02)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
              >
                <div className="flex items-center gap-3">
                  {result.status === 'passed' ? <CheckCircle size={16} style={{ color: '#00e676' }} /> :
                   result.status === 'failed' ? <XCircle size={16} style={{ color: '#ff1744' }} /> :
                   <AlertTriangle size={16} style={{ color: '#ff9100' }} />}
                  <div>
                    <span style={{ fontSize: 14, fontWeight: 500 }}>{result.name}</span>
                    <div style={{ fontSize: 11, color: '#556677', marginTop: 2 }}>
                      {result.duration_seconds?.toFixed(2)}s
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`status-badge ${result.status === 'passed' ? 'passed' : result.status === 'failed' ? 'failed' : 'error'}`}>
                    {result.status}
                  </span>
                  {expandedResults.has(result.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </div>
              </div>

              {expandedResults.has(result.id) && (
                <div style={{ padding: '0 16px 16px' }}>
                  {result.error_message && (
                    <div className="mb-2">
                      <div style={{ fontSize: 11, color: '#ff1744', marginBottom: 4 }}>错误信息:</div>
                      <pre style={{
                        background: 'rgba(255,23,68,0.05)',
                        border: '1px solid rgba(255,23,68,0.15)',
                        borderRadius: 6,
                        padding: 12,
                        fontSize: 12,
                        overflow: 'auto',
                        maxHeight: 200,
                        color: '#ff6b6b',
                      }}>{result.error_message}</pre>
                    </div>
                  )}
                  {result.log_text && (
                    <div>
                      <div style={{ fontSize: 11, color: '#8899aa', marginBottom: 4 }}>执行日志:</div>
                      <pre style={{
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(0,229,255,0.08)',
                        borderRadius: 6,
                        padding: 12,
                        fontSize: 12,
                        overflow: 'auto',
                        maxHeight: 300,
                        color: '#8899aa',
                      }}>{result.log_text}</pre>
                    </div>
                  )}
                  {result.screenshot_path && (
                    <div className="mt-3">
                      <div className="flex items-center gap-2 mb-2" style={{ fontSize: 12, color: '#556677' }}>
                        <Camera size={14} />
                        <span>失败截图</span>
                      </div>
                      <img
                        src={testRunApi.getScreenshotUrl(runId, result.id)}
                        alt="失败截图"
                        style={{
                          maxWidth: '100%',
                          maxHeight: 400,
                          borderRadius: 8,
                          border: '1px solid rgba(255,23,68,0.2)',
                          cursor: 'pointer',
                        }}
                        onClick={() => window.open(testRunApi.getScreenshotUrl(runId, result.id), '_blank')}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ========== 测试运行列表（分页 + 搜索 + 删除）==========
function TestRunList() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const pageSize = 15

  function loadRuns() {
    const params = { page, page_size: pageSize }
    if (statusFilter) params.status = statusFilter
    testRunApi.list(params)
      .then(res => {
        setRuns(res.items || [])
        setTotal(res.total || 0)
      })
      .catch(() => toast.error('加载失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadRuns() }, [page, statusFilter])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const goToRun = (id) => {
      window.location.href = `/test-runs?id=${id}`
  }

  async function handleDelete(e, id) {
    e.stopPropagation()
    if (!confirm('确定删除此测试运行记录？')) return
    try {
      await testRunApi.delete(id)
      toast.success('已删除')
      loadRuns()
    } catch (err) {
      toast.error(err.message)
    }
  }

  // 客户端搜索过滤
  const filtered = runs.filter(r =>
    !searchText || (r.name && r.name.toLowerCase().includes(searchText.toLowerCase()))
  )

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h1 className="text-2xl font-bold title-line" style={{ color: '#e0e8f0' }}>测试运行</h1>
        <p style={{ color: '#8899aa', fontSize: 13, marginTop: 8 }}>共 {total} 条记录</p>
      </div>

      {/* 搜索 + 过滤 */}
      <div className="flex items-center gap-3">
        <div className="flex items-center flex-1 cyber-input" style={{ padding: '4px 14px', maxWidth: 320 }}>
          <Search size={16} style={{ color: '#556677', flexShrink: 0 }} />
          <input className="bg-transparent border-none outline-none flex-1" style={{ color: '#e0e8f0', fontSize: 14, paddingLeft: 8 }}
            placeholder="搜索测试运行名称..."
            value={searchText} onChange={(e) => setSearchText(e.target.value)} />
        </div>
        <select className="cyber-select" style={{ width: 120 }} value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}>
          <option value="">全部状态</option>
          <option value="pending">等待中</option>
          <option value="running">运行中</option>
          <option value="passed">通过</option>
          <option value="failed">失败</option>
          <option value="error">错误</option>
          <option value="cancelled">已取消</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="loading-spinner" /></div>
      ) : filtered.length === 0 ? (
        <div className="cyber-card p-12 text-center" style={{ color: '#556677' }}>
          <Clock size={48} className="mx-auto mb-3" style={{ opacity: 0.3 }} />
          <p style={{ fontSize: 14 }}>{searchText || statusFilter ? '没有匹配的记录' : '还没有测试运行记录'}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(run => (
            <div key={run.id}
              className="cyber-card p-4 flex items-center justify-between cursor-pointer transition-all hover:border-cyan-500/30"
              onClick={() => goToRun(run.id)}>
              <div className="flex items-center gap-3 flex-1 min-w-0">
                {run.status === 'passed' ? <CheckCircle size={20} style={{ color: '#00e676' }} /> :
                 run.status === 'failed' ? <XCircle size={20} style={{ color: '#ff1744' }} /> :
                 run.status === 'running' ? <RefreshCw size={20} style={{ color: '#00e5ff' }} /> :
                 <Clock size={20} style={{ color: '#8899aa' }} />}
                <div className="min-w-0">
                  <div style={{ fontSize: 14, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.name || `运行 #${run.id}`}
                  </div>
                  <div style={{ fontSize: 11, color: '#556677' }}>
                    项目 #{run.project_id} | {run.trigger_mode} | {new Date(run.created_at).toLocaleString('zh-CN')}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                <div className="text-right">
                  <div style={{ fontSize: 12, color: '#8899aa' }}>{run.passed_cases || 0}/{run.total_cases || 0}</div>
                  {run.duration_seconds > 0 && (
                    <div style={{ fontSize: 11, color: '#556677' }}>{run.duration_seconds.toFixed(1)}s</div>
                  )}
                </div>
                <span className={`status-badge ${run.status}`}>{run.status}</span>
                <button className="p-1.5 rounded transition-all" style={{ color: '#556677' }}
                  onClick={(e) => handleDelete(e, run.id)}
                  onMouseEnter={(e) => e.currentTarget.style.color = '#ff1744'}
                  onMouseLeave={(e) => e.currentTarget.style.color = '#556677'}
                  title="删除">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button className="cyber-button" style={{ fontSize: 12, padding: '6px 12px' }}
            disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>
            <ChevronLeft size={14} /> 上一页
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
            <button key={p} className="cyber-button" style={{
              fontSize: 12, padding: '6px 12px', minWidth: 32,
              background: p === page ? 'rgba(0,229,255,0.2)' : undefined,
              borderColor: p === page ? 'rgba(0,229,255,0.5)' : undefined,
            }} onClick={() => setPage(p)}>{p}</button>
          ))}
          <button className="cyber-button" style={{ fontSize: 12, padding: '6px 12px' }}
            disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
            下一页 <ChevronRight size={14} />
          </button>
          <span style={{ fontSize: 12, color: '#556677', marginLeft: 8 }}>
            {page}/{totalPages} 页
          </span>
        </div>
      )}
    </div>
  )
}
