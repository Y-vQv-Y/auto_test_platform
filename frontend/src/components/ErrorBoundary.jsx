import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#0a1628] flex items-center justify-center p-8">
          <div className="bg-[#0f1923] border border-red-500/20 rounded-xl p-8 max-w-lg w-full text-center">
            <div className="text-red-400 text-5xl mb-4">!</div>
            <h1 className="text-white text-xl font-semibold mb-2">页面出错了</h1>
            <p className="text-gray-400 text-sm mb-4">
              {this.state.error?.message || '发生了未知错误'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.href = '/'
              }}
              className="px-6 py-2 bg-[#00e5ff] text-[#0a1628] rounded-lg font-medium hover:bg-[#00e5ff]/80 transition-colors"
            >
              返回首页
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
