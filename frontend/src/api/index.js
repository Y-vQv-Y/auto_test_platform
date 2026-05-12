/**
 * API 客户端 - 与后端通信
 *
 * 连接方式（由 VITE_API_BASE_URL 控制）：
 *   - 空字符串（默认） → 同源访问，适用于 Vite Proxy 或 Nginx 反向代理
 *   - 完整 URL         → 前后端分离部署，前端构建时注入后端地址
 *
 * 开发环境：VITE_API_BASE_URL=''（使用 vite.config.js 中的 proxy）
 * 生产环境：构建时传入 --build-arg VITE_API_BASE_URL=https://api.example.com
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const BASE_URL = `${API_BASE_URL}/api/v1`

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const { headers: optHeaders, ...rest } = options
  const config = {
    headers: { 'Content-Type': 'application/json', ...optHeaders },
    ...rest,
  }

  try {
    const response = await fetch(url, config)
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
      throw new Error(error.detail || `请求失败: ${response.status}`)
    }
    // 处理二进制响应
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('text/html')) {
      return await response.text()
    }
    if (contentType.includes('application/json')) {
      return await response.json()
    }
    return await response.text()
  } catch (error) {
    if (error.message.includes('Failed to fetch')) {
      throw new Error('无法连接到服务器，请检查后端是否运行')
    }
    throw error
  }
}

// ========== 项目 API ==========
export const projectApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/projects${qs ? `?${qs}` : ''}`)
  },
  get: (id) => request(`/projects/${id}`),
  create: (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  uploadSource: async (id, file) => {
    const formData = new FormData()
    formData.append('file', file)
    const apiBase = import.meta.env.VITE_API_BASE_URL || ''
    const url = `${apiBase}/api/v1/projects/${id}/upload`
    const response = await fetch(url, { method: 'POST', body: formData })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
      throw new Error(err.detail || '上传失败')
    }
    return response.json()
  },
}

// ========== 测试运行 API ==========
export const testRunApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/test-runs${qs ? `?${qs}` : ''}`)
  },
  get: (id) => request(`/test-runs/${id}`),
  create: (projectId, name = '自动化测试') => {
    const qs = new URLSearchParams({ project_id: projectId, name }).toString()
    return request(`/test-runs?${qs}`, { method: 'POST' })
  },
  generate: (runId, data) => request(`/test-runs/${runId}/generate`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  execute: (runId, data) => request(`/test-runs/${runId}/execute`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  cancel: (runId) => request(`/test-runs/${runId}/cancel`, { method: 'POST' }),
  delete: (runId) => request(`/test-runs/${runId}`, { method: 'DELETE' }),
  getReport: (runId) => request(`/test-runs/${runId}/report`),
  getReportHtml: (runId) => request(`/test-runs/${runId}/report/html`),
  getReportHtmlUrl: (runId) => `${API_BASE_URL}/api/v1/test-runs/${runId}/report/html`,
  exportReportUrl: (runId) => `${API_BASE_URL}/api/v1/test-runs/${runId}/export-report`,
  exportExcelUrl: (runId) => `${API_BASE_URL}/api/v1/test-runs/${runId}/export-excel`,
  getScreenshotUrl: (runId, resultId) => `${API_BASE_URL}/api/v1/test-runs/${runId}/screenshot/${resultId}`,
  connectWs: (runId) => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || ''
    if (apiBase) {
      // 前后端分离部署：WebSocket 连接到后端地址
      const wsBase = apiBase.replace(/^http/, 'ws')
      return new WebSocket(`${wsBase}/api/v1/test-runs/ws/${runId}`)
    }
    // 同源部署：使用当前页面 host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return new WebSocket(`${protocol}//${window.location.host}/api/v1/test-runs/ws/${runId}`)
  },
}

// ========== AI 配置 API ==========
export const aiConfigApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/ai-configs${qs ? `?${qs}` : ''}`)
  },
  get: (id) => request(`/ai-configs/${id}`),
  create: (data) => request('/ai-configs', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/ai-configs/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id) => request(`/ai-configs/${id}`, { method: 'DELETE' }),
  testConnection: (id) => request(`/ai-configs/${id}/test`, { method: 'POST' }),
}

// ========== Jenkins API ==========
export const jenkinsApi = {
  listConfigs: () => request('/jenkins/configs'),
  createConfig: (data) => request('/jenkins/configs', { method: 'POST', body: JSON.stringify(data) }),
  updateConfig: (id, data) => request(`/jenkins/configs/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteConfig: (id) => request(`/jenkins/configs/${id}`, { method: 'DELETE' }),
  testConnection: (id) => request(`/jenkins/configs/${id}/test`, { method: 'POST' }),
  triggerJob: (id, params = {}) => request(`/jenkins/configs/${id}/trigger`, {
    method: 'POST',
    body: JSON.stringify(params),
  }),
}

// ========== 系统/安全 API ==========
export const systemApi = {
  dashboard: () => request('/dashboard'),
  securitySettings: () => request('/settings/security'),
  updateUrlWhitelist: (urls) => request('/settings/security/url-whitelist', {
    method: 'PUT',
    body: JSON.stringify({ urls }),
  }),
  updateUrlWhitelistToggle: (enabled) => {
    const qs = new URLSearchParams({ enabled }).toString()
    return request(`/settings/security/url-whitelist-toggle?${qs}`, { method: 'PUT' })
  },
  updateReadonlyMode: (enabled) => {
    const qs = new URLSearchParams({ enabled }).toString()
    return request(`/settings/security/readonly?${qs}`, { method: 'PUT' })
  },
  securityLogs: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/settings/security/logs${qs ? `?${qs}` : ''}`)
  },
  info: () => request('/system/info'),
}

// ========== 测试用例 API ==========
export const testCaseApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/test-cases${qs ? `?${qs}` : ''}`)
  },
  getCode: (id) => request(`/test-cases/${id}/code`),
  update: (id, data) => request(`/test-cases/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
    headers: { 'Content-Type': 'application/json' },
  }),
  delete: (id) => request(`/test-cases/${id}`, { method: 'DELETE' }),
  exportExcelUrl: (projectId) => {
    const qs = projectId ? `?project_id=${projectId}` : ''
    return `${API_BASE_URL}/api/v1/test-cases/export/excel${qs}`
  },
}

// ========== 验证码/登录 API ==========
export const captchaApi = {
  login: (projectId) => request(`/captcha/login/${projectId}`, { method: 'POST' }),
  status: (projectId) => request(`/captcha/status/${projectId}`),
  clearLogin: (projectId) => request(`/captcha/login/${projectId}`, { method: 'DELETE' }),
  saveCookies: (projectId, cookies) => request(`/captcha/cookies/${projectId}`, {
    method: 'POST', body: JSON.stringify({ cookies }),
  }),
  checkSession: (projectId) => request(`/captcha/check_session/${projectId}`, { method: 'POST' }),
  refreshLogin: (projectId) => request(`/captcha/refresh_login/${projectId}`, { method: 'POST' }),
  autoLogin: (projectId, data) => request(`/captcha/auto_login/${projectId}`, {
    method: 'POST', body: JSON.stringify(data),
  }),
  getAutoLoginConfig: (projectId) => request(`/captcha/auto_login_config/${projectId}`),
}
