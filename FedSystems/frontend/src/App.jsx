import { useEffect, useState } from 'react'
import './App.css'

const pages = {
  home: 'home',
  sessions: 'sessions',
}

const navigationItems = [
  { key: pages.home, label: 'Home' },
  { key: pages.sessions, label: 'Sessions Manager' },
]

function HomePage({
  apiUrl,
  backendStatus,
  onRefresh,
  sftpUsers,
  sftpLoading,
  achBanks,
  achBanksLoading,
  bankBalances,
  bankBalanceLoadingByRtn,
}) {
  const formatCentsToUsd = (value) => {
    const numeric = Number(value ?? 0)
    if (Number.isNaN(numeric)) return '$0.00'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric / 100)
  }

  const healthClasses =
    backendStatus.variant === 'ok'
      ? 'bg-success-subtle border-success-subtle text-success-emphasis'
      : backendStatus.variant === 'error'
        ? 'bg-danger-subtle border-danger-subtle text-danger-emphasis'
        : 'bg-secondary-subtle border-secondary-subtle text-secondary-emphasis'

  return (
    <main className="container-fluid py-4 py-lg-5">
      <section className="card shadow-sm border-0 rounded-4 bg-white">
        <div className="card-body p-4 p-lg-5">
          <div className="d-flex flex-column flex-lg-row justify-content-between gap-3 align-items-lg-start">
            <div>
              <span className="badge text-bg-primary mb-3">Home</span>
              <h1 className="display-6 fw-bold mb-2">Fed Systems Dashboard</h1>
              <p className="text-body-secondary mb-0">
                Monitor backend health and jump into the sessions manager from a simple shared
                shell.
              </p>
            </div>

            <div className={`border rounded-3 p-3 d-flex align-items-center gap-3 ${healthClasses}`}>
              <div className="min-w-0">
                <div className="text-uppercase small fw-semibold opacity-75">Backend Health</div>
                <div className="fw-semibold text-break">{backendStatus.message}</div>
              </div>

              <button type="button" className="btn btn-sm btn-light fw-semibold" onClick={onRefresh}>
                Refresh
              </button>
            </div>
          </div>

          <div className="row g-3 mt-1">
            <div className="col-12 col-lg-6">
              <div className="card h-100 border-0 bg-body-tertiary rounded-4">
                <div className="card-body p-3 p-lg-4">
                  <div className="text-uppercase text-body-secondary small fw-semibold mb-2">
                    ACH API Endpoint
                  </div>
                  <div className="fw-semibold text-break">{apiUrl}</div>
                </div>
              </div>
            </div>
            <div className="col-12 col-lg-6">
              <div className="card h-100 border-0 rounded-4" style={{ backgroundColor: '#f4effc' }}>
                <div className="card-body p-3 p-lg-4">
                  <div className="text-uppercase text-body-secondary small fw-semibold mb-2">
                    FedNow API Endpoint
                  </div>
                  <span className="badge rounded-pill text-white fw-semibold" style={{ backgroundColor: '#6f42c1' }}>
                    WIP
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="row g-3 mt-3">
            <div className="col-12">
              <div className="card border-0 bg-body-tertiary rounded-4">
                <div className="card-body p-3 p-lg-4">
                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <div className="text-uppercase text-body-secondary small fw-semibold">SFTP Users</div>
                  </div>

                  {sftpLoading ? (
                    <div>Loading SFTP users...</div>
                  ) : (
                    <ul className="list-group">
                      {(!sftpUsers || sftpUsers.length === 0) && (
                        <li className="list-group-item">No SFTP users found</li>
                      )}
                      {(sftpUsers || []).map((u) => (
                        <li key={u.username} className="list-group-item d-flex justify-content-between align-items-start">
                          <div className="ms-0 flex-grow-1 me-3">
                            <div className="fw-semibold">{u.username}</div>
                            <div className="small text-muted">{u.home} • {u.shell}</div>
                            {u.public_key ? (
                              <details className="mt-2">
                                <summary className="small text-uppercase text-body-secondary fw-semibold cursor-pointer">
                                  Public Key
                                </summary>
                                <code className="d-block text-break small bg-body rounded-3 border p-2 mt-2">
                                  {u.public_key}
                                </code>
                              </details>
                            ) : null}
                          </div>
                          <div className="text-end">
                            <span className="badge bg-secondary rounded-pill">{u.uid}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="row g-3 mt-3">
            <div className="col-12">
              <div className="card border-0 bg-body-tertiary rounded-4">
                <div className="card-body p-3 p-lg-4">
                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <div className="text-uppercase text-body-secondary small fw-semibold">Registered Banks</div>
                  </div>

                  {achBanksLoading ? (
                    <div>Loading registered banks...</div>
                  ) : (
                    <div className="row g-3">
                      {(!achBanks || achBanks.length === 0) && (
                        <div className="col-12">
                          <div className="alert alert-light border mb-0">No registered banks found</div>
                        </div>
                      )}

                      {(achBanks || []).map((bank) => (
                        <div className="col-12 col-lg-6" key={bank.primary_routing_transit_number ?? bank.sftp_username}>
                          <div className="card h-100 border-0 bg-white rounded-4 shadow-sm">
                            <div className="card-body">
                              <div className="d-flex justify-content-between align-items-start gap-3">
                                <div>
                                  <div className="fw-semibold mb-1">{bank.legal_name || 'Unnamed Bank'}</div>
                                  <div className="small text-muted">SFTP: {bank.sftp_username || '-'}</div>
                                </div>
                                <div className="text-end">
                                  <div className="small text-uppercase text-body-secondary fw-semibold">Current Balance</div>
                                  <div className="fw-bold">
                                    {bank.master_account_rtn && bankBalanceLoadingByRtn?.[String(bank.master_account_rtn)]
                                      ? 'Loading...'
                                      : bank.master_account_rtn && bankBalances?.[String(bank.master_account_rtn)]
                                        ? formatCentsToUsd(bankBalances[String(bank.master_account_rtn)].current_balance)
                                        : '-'}
                                  </div>
                                  <span className={`badge mt-1 ${bank.ach_participant ? 'text-bg-success' : 'text-bg-secondary'}`}>
                                    {bank.ach_participant ? 'ACH Active' : 'Not Active'}
                                  </span>
                                </div>
                              </div>

                              <div className="mt-3 small">
                                <div><span className="text-body-secondary">Primary RTN:</span> {bank.primary_routing_transit_number ?? '-'}</div>
                                <div><span className="text-body-secondary">Master RTN:</span> {bank.master_account_rtn ?? '-'}</div>
                                <div><span className="text-body-secondary">Type:</span> {bank.participant_type || '-'}</div>
                                <div><span className="text-body-secondary">Restricted:</span> {bank.restricted ? 'Yes' : 'No'}</div>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}

function SessionsPage() {
  return (
    <main className="container-fluid py-4 py-lg-5">
      <section className="card shadow-sm border-0 rounded-4 bg-white">
        <div className="card-body p-4 p-lg-5">
          <span className="badge text-bg-secondary mb-3">Sessions Manager</span>
          <h1 className="display-6 fw-bold mb-2">Sessions Manager</h1>
          <p className="text-body-secondary mb-4">
            TODO: This page will hold session tools
          </p>
        </div>
      </section>
    </main>
  )
}

function App() {
  const [backendStatus, setBackendStatus] = useState({
    message: 'Loading...',
    variant: 'loading',
  })
  const [apiUrl] = useState(() => {
    return import.meta.env.VITE_ACH_API_BASE_URL || 'http://localhost:8001'
  })
  const fmtStatus = (data) => {
    if (!data) return 'ok'
    if (typeof data === 'string') return data
    if (typeof data === 'object' && 'status' in data) return String(data.status)
    return 'ok'
  }
  const [page, setPage] = useState(() => {
    const hash = window.location.hash.replace('#', '')
    return pages[hash] || pages.home
  })

  const [sftpUsers, setSftpUsers] = useState([])
  const [sftpLoading, setSftpLoading] = useState(false)
  const [achBanks, setAchBanks] = useState([])
  const [achBanksLoading, setAchBanksLoading] = useState(false)
  const [bankBalances, setBankBalances] = useState({})
  const [bankBalanceLoadingByRtn, setBankBalanceLoadingByRtn] = useState({})

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '')
      setPage(pages[hash] || pages.home)
    }

    window.addEventListener('hashchange', handleHashChange)
    handleHashChange()

    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    if (page !== pages.home) {
      return
    }

    const controller = new AbortController()

    fetch(`${apiUrl}/health`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }

        return res.json()
      })
        .then((data) => {
          setBackendStatus({
            message: fmtStatus(data),
            variant: 'ok',
          })
        })
      .catch((err) => {
        if (err.name === 'AbortError') {
          return
        }

        setBackendStatus({
          message: err.message || 'Failed to fetch',
          variant: 'error',
        })
      })

    return () => controller.abort()
  }, [apiUrl, page])

  useEffect(() => {
    if (page !== pages.home) return

    setSftpLoading(true)
    fetch(`${apiUrl}/api/sftp-users`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => setSftpUsers(data.sftp_users || []))
      .catch(() => setSftpUsers([]))
      .finally(() => setSftpLoading(false))
  }, [apiUrl, page])

  useEffect(() => {
    if (page !== pages.home) return

    setAchBanksLoading(true)
    fetch(`${apiUrl}/api/ach-banks`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => setAchBanks(data.banks || []))
      .catch(() => setAchBanks([]))
      .finally(() => setAchBanksLoading(false))
  }, [apiUrl, page])

  useEffect(() => {
    if (page !== pages.home) return

    const rtNs = (achBanks || [])
      .map((b) => b.master_account_rtn)
      .filter((rtn) => rtn !== null && rtn !== undefined)
      .map((rtn) => String(rtn))

    if (rtNs.length === 0) {
      setBankBalances({})
      setBankBalanceLoadingByRtn({})
      return
    }

    const loadingMap = Object.fromEntries(rtNs.map((rtn) => [rtn, true]))
    setBankBalanceLoadingByRtn(loadingMap)

    Promise.all(
      rtNs.map((rtn) =>
        fetch(`${apiUrl}/api/current-balance?master_account_rtn=${encodeURIComponent(rtn)}`)
          .then((res) => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            return res.json()
          })
          .then((data) => ({ rtn, data }))
          .catch(() => ({ rtn, data: null }))
      )
    ).then((results) => {
      const balances = {}
      const nextLoading = {}
      results.forEach(({ rtn, data }) => {
        balances[rtn] = data
        nextLoading[rtn] = false
      })
      setBankBalances(balances)
      setBankBalanceLoadingByRtn(nextLoading)
    })
  }, [apiUrl, page, achBanks])

  const refreshBackendStatus = () => {
    setBackendStatus({
      message: 'Loading...',
      variant: 'loading',
    })

    fetch(`${apiUrl}/health`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }

        return res.json()
      })
        .then((data) => {
          setBackendStatus({
            message: fmtStatus(data),
            variant: 'ok',
          })
        })
      .catch((err) => {
        setBackendStatus({
          message: err.message || 'Failed to fetch',
          variant: 'error',
        })
      })
  }

  const navigateTo = (nextPage) => {
    window.location.hash = nextPage
  }

  const renderPage = () => {
    if (page === pages.sessions) {
      return <SessionsPage />
    }

    return (
      <HomePage
        apiUrl={apiUrl}
        backendStatus={backendStatus}
        onRefresh={refreshBackendStatus}
        sftpUsers={sftpUsers}
        sftpLoading={sftpLoading}
        achBanks={achBanks}
        achBanksLoading={achBanksLoading}
        bankBalances={bankBalances}
        bankBalanceLoadingByRtn={bankBalanceLoadingByRtn}
      />
    )
  }

  return (
    <div className="container py-3">
      <nav className="navbar navbar-dark bg-dark rounded-4 border-top border-primary border-4 shadow-sm px-3 py-2" aria-label="Primary navigation">
        <div className="d-flex flex-wrap gap-2">
          {navigationItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={page === item.key ? 'btn btn-light fw-semibold' : 'btn btn-outline-light'}
              onClick={() => navigateTo(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </nav>

      {renderPage()}
    </div>
  )
}

export default App
