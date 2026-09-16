const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('token')
}

function clearAuth() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

async function request(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const opts = { method, headers }
  if (body !== null) {
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE_URL}${path}`, opts)

  if (res.status === 401) {
    clearAuth()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  let data = null
  const text = await res.text()
  if (text) {
    data = JSON.parse(text)
  }

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`
    if (data?.detail) {
      if (Array.isArray(data.detail)) {
        message = data.detail.map((d) => d.msg || String(d)).join('; ')
      } else if (typeof data.detail === 'string') {
        message = data.detail
      }
    }
    const error = new Error(message)
    error.status = res.status
    error.data = data
    throw error
  }

  return data
}

const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
}

export default api
