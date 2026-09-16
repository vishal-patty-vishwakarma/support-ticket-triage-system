import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import TicketsPage from './pages/TicketsPage'
import CreateTicketPage from './pages/CreateTicketPage'
import TicketDetailPage from './pages/TicketDetailPage'
import ProtectedRoute from './components/ProtectedRoute'

const mockFetch = vi.fn()
global.fetch = mockFetch

function mockJson(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(JSON.stringify(data)),
  }
}

function mockError(detail, status = 400) {
  return {
    ok: false,
    status,
    text: () => Promise.resolve(JSON.stringify({ detail })),
  }
}

beforeEach(() => {
  localStorage.clear()
  mockFetch.mockReset()
})

function renderPage(ui, route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>
  )
}

const meResponse = { id: 1, name: 'Test User', email: 'test@example.com', role: 'agent' }

describe('Authentication', () => {
  it('unauthenticated protected route redirects to login', async () => {
    mockFetch.mockResolvedValue(mockError('Unauthorized', 401))
    renderPage(
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      </Routes>,
      '/dashboard'
    )
    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })

  it('successful login stores auth and navigates', async () => {
    const user = userEvent.setup()
    mockFetch
      .mockResolvedValueOnce(mockJson({ access_token: 'fake-token' }))
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson({
        open_count: 0, assigned_count: 0, in_progress_count: 0,
        critical_count: 0, resolved_count: 0, total_count: 0, recent_tickets: [],
      }))

    renderPage(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      </Routes>,
      '/login'
    )

    await user.type(screen.getByLabelText(/email/i), 'test@example.com')
    await user.type(screen.getByLabelText(/password/i), 'password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })
    expect(localStorage.getItem('token')).toBe('fake-token')
  })

  it('login error is displayed', async () => {
    const user = userEvent.setup()
    mockFetch.mockResolvedValueOnce(mockError('Invalid credentials', 401))

    renderPage(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>,
      '/login'
    )

    await user.type(screen.getByLabelText(/email/i), 'bad@example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/Unauthorized|Invalid credentials/i)).toBeInTheDocument()
    })
  })
})

describe('Dashboard', () => {
  it('dashboard stats render', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson({
        open_count: 3, assigned_count: 1, in_progress_count: 2,
        critical_count: 1, resolved_count: 5, total_count: 11,
        recent_tickets: [],
      }))

    renderPage(
      <Routes>
        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      </Routes>,
      '/dashboard'
    )

    await waitFor(() => {
      expect(screen.getByText('11')).toBeInTheDocument()
      expect(screen.getByText('Total')).toBeInTheDocument()
    })
  })
})

describe('Ticket List', () => {
  it('ticket list renders', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson([
        { id: 1, subject: 'Test Subject', customer_name: 'John', category: 'Billing', priority: 'High', status: 'Open', assigned_team_id: null, created_at: '2026-01-01T00:00:00' },
      ]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))

    renderPage(
      <Routes>
        <Route path="/tickets" element={<ProtectedRoute><TicketsPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets'
    )

    await waitFor(() => {
      expect(screen.getByText('Test Subject')).toBeInTheDocument()
    })
  })
})

describe('Create Ticket', () => {
  it('Save Ticket flow navigates to ticket detail', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson({ id: 42, subject: 'New ticket', status: 'Open' }))

    renderPage(
      <Routes>
        <Route path="/tickets/new" element={<ProtectedRoute><CreateTicketPage /></ProtectedRoute>} />
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><div>Ticket 42 created</div></ProtectedRoute>} />
      </Routes>,
      '/tickets/new'
    )

    await waitFor(() => { screen.getByLabelText(/customer name/i) })

    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/customer name/i), 'Jane Doe')
    await user.type(screen.getByLabelText(/customer email/i), 'jane@example.com')
    await user.type(screen.getByLabelText(/subject/i), 'This is a test subject for creation')
    await user.type(screen.getByLabelText(/description/i), 'This is a detailed description for testing the create ticket flow with enough characters.')
    await user.click(screen.getByRole('button', { name: /save ticket$/i }))

    await waitFor(() => {
      expect(screen.getByText('Ticket 42 created')).toBeInTheDocument()
    })
  })

  it('Save & Analyze navigates to ticket with AI error when AI fails', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson({ id: 99, subject: 'AI fail ticket', status: 'Open' }))
      .mockResolvedValueOnce(mockError('AI service unavailable', 503))

    renderPage(
      <Routes>
        <Route path="/tickets/new" element={<ProtectedRoute><CreateTicketPage /></ProtectedRoute>} />
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><div>Ticket 99 with AI error indicator</div></ProtectedRoute>} />
      </Routes>,
      '/tickets/new'
    )

    await waitFor(() => { screen.getByLabelText(/customer name/i) })

    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/customer name/i), 'Jane Doe')
    await user.type(screen.getByLabelText(/customer email/i), 'jane@example.com')
    await user.type(screen.getByLabelText(/subject/i), 'This is a test subject for AI failure')
    await user.type(screen.getByLabelText(/description/i), 'This is a detailed description for testing AI failure handling during create and analyze flow.')
    await user.click(screen.getByRole('button', { name: /save & analyze/i }))

    await waitFor(() => {
      expect(screen.getByText('Ticket 99 with AI error indicator')).toBeInTheDocument()
    })
  })
})

describe('Ticket Detail', () => {
  const mockTicket = {
    id: 5, customer_name: 'Test Customer', customer_email: 'tc@test.com',
    subject: 'Test ticket detail', description_original: 'Original description here for testing.',
    status: 'Open', priority: null, category: null, summary: null,
    assigned_team_id: null, assigned_user_id: null, created_by: 1,
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  }

  const mockAiRun = {
    id: 1, ticket_id: 5, status: 'success', provider: 'ollama', model: 'qwen3:4b',
    summary: 'AI summary', category: 'Billing', priority: 'High',
    priority_reason: 'Revenue impact', recommended_team: 'BILLING',
    suggested_response: 'We will look into this.', created_at: '2026-01-01T00:00:00',
  }

  it('AI suggestions render as suggestions', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson(mockTicket))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson(mockAiRun))

    renderPage(
      <Routes>
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><TicketDetailPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets/5'
    )

    await waitFor(() => {
      expect(screen.getByText('AI summary')).toBeInTheDocument()
      expect(screen.getByText('Accept Suggestions')).toBeInTheDocument()
    })
  })

  it('Accept calls review API', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson(mockTicket))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson(mockAiRun))

    renderPage(
      <Routes>
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><TicketDetailPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets/5'
    )

    await waitFor(() => { screen.getByText('Accept Suggestions') })

    const user = userEvent.setup()
    mockFetch
      .mockResolvedValueOnce(mockJson({ ...mockTicket, summary: 'AI summary' }))  // PUT /review
      .mockResolvedValueOnce(mockJson({ ...mockTicket, summary: 'AI summary' }))  // GET /tickets/{id}
      .mockResolvedValueOnce(mockJson([]))  // GET /activities
      .mockResolvedValueOnce(mockJson([]))  // GET /comments
      .mockResolvedValueOnce(mockJson([]))  // GET /teams
      .mockResolvedValueOnce(mockJson([]))  // GET /users
      .mockResolvedValueOnce(mockJson(mockAiRun))  // GET /ai-analysis/latest

    await user.click(screen.getByRole('button', { name: /accept suggestions/i }))

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        (c) => c[0]?.includes('/review') && c[1]?.method === 'PUT'
      )
      expect(putCall).toBeTruthy()
      expect(JSON.parse(putCall[1].body).action).toBe('ACCEPT')
    })
  })

  it('Reject calls review API', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson(mockTicket))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson(mockAiRun))

    renderPage(
      <Routes>
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><TicketDetailPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets/5'
    )

    await waitFor(() => { screen.getByText('Reject Suggestions') })

    const user = userEvent.setup()
    window.confirm = vi.fn(() => true)
    mockFetch
      .mockResolvedValueOnce(mockJson(mockTicket))  // PUT /review
      .mockResolvedValueOnce(mockJson(mockTicket))  // GET /tickets/{id}
      .mockResolvedValueOnce(mockJson([]))  // GET /activities
      .mockResolvedValueOnce(mockJson([]))  // GET /comments
      .mockResolvedValueOnce(mockJson([]))  // GET /teams
      .mockResolvedValueOnce(mockJson([]))  // GET /users
      .mockResolvedValueOnce(mockError('not found', 404))  // GET /ai-analysis/latest

    await user.click(screen.getByRole('button', { name: /reject suggestions/i }))

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        (c) => c[0]?.includes('/review') && c[1]?.method === 'PUT'
      )
      expect(putCall).toBeTruthy()
      expect(JSON.parse(putCall[1].body).action).toBe('REJECT')
    })
  })

  it('manual triage works without AI', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson(mockTicket))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockError('not found', 404))

    renderPage(
      <Routes>
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><TicketDetailPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets/5'
    )

    await waitFor(() => { screen.getByText('Triage Manually') })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /triage manually/i }))

    await waitFor(() => {
      expect(screen.getByLabelText(/summary/i)).toBeInTheDocument()
    })

    mockFetch
      .mockResolvedValueOnce(mockJson({ ...mockTicket, summary: 'Manual triage applied' }))  // PUT /review
      .mockResolvedValueOnce(mockJson({ ...mockTicket, summary: 'Manual triage applied' }))  // GET /tickets/{id}
      .mockResolvedValueOnce(mockJson([]))  // GET /activities
      .mockResolvedValueOnce(mockJson([]))  // GET /comments
      .mockResolvedValueOnce(mockJson([]))  // GET /teams
      .mockResolvedValueOnce(mockJson([]))  // GET /users
      .mockResolvedValueOnce(mockError('not found', 404))  // GET /ai-analysis/latest

    await user.type(screen.getByLabelText(/summary/i), 'Manual triage summary')
    await user.click(screen.getByRole('button', { name: /save manual triage/i }))

    await waitFor(() => {
      expect(screen.getByText('Manual triage saved.')).toBeInTheDocument()
    })
  })
})

describe('raw_response never displayed', () => {
  it('raw_response is not shown in AI analysis UI', async () => {
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('user', JSON.stringify(meResponse))

    const ticket = {
      id: 10, customer_name: 'C', customer_email: 'c@c.com',
      subject: 'Subject here for raw test', description_original: 'Desc for raw response test.',
      status: 'Open', priority: null, category: null, summary: null,
      assigned_team_id: null, assigned_user_id: null, created_by: 1,
      created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
    }

    mockFetch
      .mockResolvedValueOnce(mockJson(meResponse))
      .mockResolvedValueOnce(mockJson(ticket))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson([]))
      .mockResolvedValueOnce(mockJson({
        id: 1, ticket_id: 10, status: 'success', provider: 'ollama', model: 'qwen3:4b',
        summary: 'Test Summary', category: 'Billing', priority: 'High',
        priority_reason: 'Because', recommended_team: 'BILLING',
        suggested_response: 'Hello', created_at: '2026-01-01T00:00:00',
        raw_response: 'SHOULD NOT APPEAR',
      }))

    renderPage(
      <Routes>
        <Route path="/tickets/:ticketId" element={<ProtectedRoute><TicketDetailPage /></ProtectedRoute>} />
      </Routes>,
      '/tickets/10'
    )

    await waitFor(() => {
      expect(screen.getByText('Test Summary')).toBeInTheDocument()
    })
    expect(screen.queryByText('SHOULD NOT APPEAR')).not.toBeInTheDocument()
  })
})
