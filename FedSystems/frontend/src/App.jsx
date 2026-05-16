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
  onBankAdded,
  sftpUsers,
  sftpLoading,
  achBanks,
  achBanksLoading,
  bankBalances,
  bankBalanceLoadingByRtn,
}) {
  const [isAddBankOpen, setIsAddBankOpen] = useState(false)
  const [addBankSubmitting, setAddBankSubmitting] = useState(false)
  const [addBankError, setAddBankError] = useState('')
  const [addBankForm, setAddBankForm] = useState(() => ({
    primary_routing_transit_number: '',
    legal_name: '',
    federal_employer_identification_number: '',
    master_account_rtn: '',
    net_debit_cap: '',
    sftp_username: '',
  }))

  const [isTransferOpen, setIsTransferOpen] = useState(false)
  const [transferSubmitting, setTransferSubmitting] = useState(false)
  const [transferError, setTransferError] = useState('')
  const [transferForm, setTransferForm] = useState(() => ({
    sender_master_account_rtn: '090000515',
    receiver_master_account_rtn: '',
    amount_cents: '',
    rail_type: 'FedWire',
    external_ref_id: '',
    effective_date: '',
  }))

  useEffect(() => {
    if (!isAddBankOpen) {
      return
    }

    setAddBankForm((current) => {
      if (current.sftp_username && sftpUsers.some((user) => user.username === current.sftp_username)) {
        return current
      }

      return {
        ...current,
        sftp_username: sftpUsers[0]?.username || '',
      }
    })
  }, [isAddBankOpen, sftpUsers])

  const openAddBankDialog = () => {
    setAddBankError('')
    setAddBankForm({
      primary_routing_transit_number: '',
      legal_name: '',
      federal_employer_identification_number: '',
      master_account_rtn: '',
      net_debit_cap: '',
      sftp_username: sftpUsers[0]?.username || '',
    })
    setIsAddBankOpen(true)
  }

  const closeAddBankDialog = () => {
    if (addBankSubmitting) {
      return
    }

    setIsAddBankOpen(false)
    setAddBankError('')
  }

  const openTransferDialog = (bankRtn) => {
    setTransferError('')
    setTransferForm({
      sender_master_account_rtn: '090000515',
      receiver_master_account_rtn: bankRtn,
      amount_cents: '',
      rail_type: 'FedWire',
      external_ref_id: '',
      effective_date: '',
    })
    setIsTransferOpen(true)
  }

  const closeTransferDialog = () => {
    if (transferSubmitting) {
      return
    }

    setIsTransferOpen(false)
    setTransferError('')
  }

  const updateTransferForm = (field, value) => {
    setTransferForm((current) => ({
      ...current,
      [field]: value,
    }))
  }

  const submitTransferForm = async (event) => {
    event.preventDefault()

    if (!transferForm.amount_cents) {
      setTransferError('Amount is required.')
      return
    }

    const amountValue = parseFloat(transferForm.amount_cents)
    if (isNaN(amountValue) || amountValue <= 0) {
      setTransferError('Amount must be a positive number.')
      return
    }

    const payload = {
      sender_master_account_rtn: transferForm.sender_master_account_rtn,
      receiver_master_account_rtn: transferForm.receiver_master_account_rtn,
      amount_cents: amountValue,
      rail_type: transferForm.rail_type,
      external_ref_id: transferForm.external_ref_id.trim() || undefined,
      effective_date: transferForm.effective_date.trim() || undefined,
    }

    setTransferSubmitting(true)
    setTransferError('')

    try {
      const response = await fetch(`${apiUrl}/api/funds-transfer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`

        try {
          const errorData = await response.json()
          errorMessage = errorData?.message || errorData?.detail || errorMessage
        } catch {
          // Keep the HTTP status message when the backend does not return JSON.
        }

        throw new Error(errorMessage)
      }

      await onBankAdded()
      setIsTransferOpen(false)
    } catch (error) {
      setTransferError(error.message || 'Failed to transfer funds')
    } finally {
      setTransferSubmitting(false)
    }
  }

  const updateAddBankForm = (field, value) => {
    setAddBankForm((current) => ({
      ...current,
      [field]: value,
    }))
  }

  const submitAddBankForm = async (event) => {
    event.preventDefault()

    if (
      !addBankForm.primary_routing_transit_number ||
      !addBankForm.legal_name.trim() ||
      !addBankForm.federal_employer_identification_number ||
      !addBankForm.master_account_rtn ||
      !addBankForm.net_debit_cap ||
      !addBankForm.sftp_username
    ) {
      setAddBankError('Fill in all fields before adding the bank.')
      return
    }

    const payload = {
      primary_routing_transit_number: addBankForm.primary_routing_transit_number.trim(),
      legal_name: addBankForm.legal_name.trim(),
      federal_employer_identification_number: addBankForm.federal_employer_identification_number.trim(),
      master_account_rtn: addBankForm.master_account_rtn.trim(),
      net_debit_cap: addBankForm.net_debit_cap.trim(),
      sftp_username: addBankForm.sftp_username,
    }

    if (
      !/^\d{9}$/.test(payload.primary_routing_transit_number) ||
      !/^\d{9}$/.test(payload.master_account_rtn) ||
      !/^\d{9}$/.test(payload.federal_employer_identification_number) ||
      !/^\d+$/.test(payload.net_debit_cap)
    ) {
      setAddBankError('Enter valid 9-digit routing numbers, valid 9-digit FEIN, and numeric net debit cap.')
      return
    }

    setAddBankSubmitting(true)
    setAddBankError('')

    try {
      const response = await fetch(`${apiUrl}/api/add-ach-bank`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`

        try {
          const errorData = await response.json()
          errorMessage = errorData?.message || errorData?.detail || errorMessage
        } catch {
          // Keep the HTTP status message when the backend does not return JSON.
        }

        throw new Error(errorMessage)
      }

      await onBankAdded()
      setIsAddBankOpen(false)
    } catch (error) {
      setAddBankError(error.message || 'Failed to add bank')
    } finally {
      setAddBankSubmitting(false)
    }
  }

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
              <a href={apiUrl + '/docs'} target="_blank" rel="noopener noreferrer" className="card h-100 border-0 bg-body-tertiary rounded-4 text-decoration-none api-docs-link">
                <div className="card-body p-3 p-lg-4">
                  <div className="text-uppercase text-body-secondary small fw-semibold mb-2">
                    ACH API Endpoint
                  </div>
                  <div className="fw-semibold text-break">{apiUrl}</div>
                </div>
              </a>
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
                    <button type="button" className="btn btn-primary btn-sm fw-semibold" onClick={openAddBankDialog}>
                      Register New Bank
                    </button>
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

                              {bank.master_account_rtn && (
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm mt-3 w-100"
                                  onClick={() => openTransferDialog(bank.master_account_rtn)}
                                >
                                  Add Funds
                                </button>
                              )}
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

          {isAddBankOpen ? (
            <div className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center p-3" style={{ zIndex: 1080 }}>
              <button
                type="button"
                className="position-absolute top-0 start-0 w-100 h-100 border-0 bg-dark"
                style={{ opacity: 0.55 }}
                aria-label="Close add bank dialog"
                onClick={closeAddBankDialog}
              />

              <div className="card shadow-lg border-0 rounded-4 position-relative w-100" style={{ maxWidth: '44rem' }}>
                <div className="card-header bg-white border-0 pt-4 px-4 px-lg-4 pb-0 d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div className="text-uppercase text-body-secondary small fw-semibold">Registered Banks</div>
                    <h2 className="h4 fw-bold mb-0 mt-1">Add New Bank</h2>
                  </div>
                  <button type="button" className="btn-close" aria-label="Close" onClick={closeAddBankDialog} />
                </div>

                <form onSubmit={submitAddBankForm}>
                  <div className="card-body p-4 p-lg-4">
                    <div className="row g-3">
                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="add-bank-primary-rtn">
                          Primary RTN (9-digit Routing Number) Warning: currently the system does not validate if the RTN is actually valid.
                        </label>
                        <input
                          id="add-bank-primary-rtn"
                          className="form-control"
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          maxLength="9"
                          value={addBankForm.primary_routing_transit_number}
                          onChange={(event) => updateAddBankForm('primary_routing_transit_number', event.target.value)}
                          disabled={addBankSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="add-bank-ein">
                          Federal EIN (9-digit FEIN Number)
                        </label>
                        <input
                          id="add-bank-ein"
                          className="form-control"
                          type="number"
                          min="0"
                          step="1"
                          value={addBankForm.federal_employer_identification_number}
                          onChange={(event) => updateAddBankForm('federal_employer_identification_number', event.target.value)}
                          disabled={addBankSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12">
                        <label className="form-label fw-semibold" htmlFor="add-bank-legal-name">
                          Legal Name
                        </label>
                        <input
                          id="add-bank-legal-name"
                          className="form-control"
                          type="text"
                          value={addBankForm.legal_name}
                          onChange={(event) => updateAddBankForm('legal_name', event.target.value)}
                          disabled={addBankSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="add-bank-master-rtn">
                          Master RTN (Usually the same as primary RTN, but can be different for some banks)
                        </label>
                        <input
                          id="add-bank-master-rtn"
                          className="form-control"
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          maxLength="9"
                          value={addBankForm.master_account_rtn}
                          onChange={(event) => updateAddBankForm('master_account_rtn', event.target.value)}
                          disabled={addBankSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="add-bank-net-debit-cap">
                          Net Debit Cap (in cents)
                        </label>
                        <input
                          id="add-bank-net-debit-cap"
                          className="form-control"
                          type="number"
                          min="0"
                          step="1"
                          value={addBankForm.net_debit_cap}
                          onChange={(event) => updateAddBankForm('net_debit_cap', event.target.value)}
                          disabled={addBankSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12">
                        <label className="form-label fw-semibold" htmlFor="add-bank-sftp-username">
                          SFTP Usernames (Although multiple banks can share the same SFTP user, it's not really recomended to do so. If you need to add a new SFTP user, check out the readme.)
                        </label>
                        <select
                          id="add-bank-sftp-username"
                          className="form-select"
                          value={addBankForm.sftp_username}
                          onChange={(event) => updateAddBankForm('sftp_username', event.target.value)}
                          disabled={addBankSubmitting || sftpUsers.length === 0}
                          required
                        >
                          <option value="" disabled>
                            {sftpUsers.length === 0 ? 'No SFTP users available' : 'Select an SFTP user'}
                          </option>
                          {sftpUsers.map((user) => (
                            <option key={user.username} value={user.username}>
                              {user.username}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {addBankError ? <div className="alert alert-danger mt-3 mb-0">{addBankError}</div> : null}
                  </div>

                  <div className="card-footer bg-white border-0 px-4 pb-4 pt-0 d-flex flex-column flex-sm-row justify-content-end gap-2">
                    <button type="button" className="btn btn-outline-secondary" onClick={closeAddBankDialog} disabled={addBankSubmitting}>
                      Cancel
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={addBankSubmitting || sftpUsers.length === 0}>
                      {addBankSubmitting ? 'Adding Bank...' : 'Add Bank'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          ) : null}

          {isTransferOpen ? (
            <div className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center p-3" style={{ zIndex: 1080 }}>
              <button
                type="button"
                className="position-absolute top-0 start-0 w-100 h-100 border-0 bg-dark"
                style={{ opacity: 0.55 }}
                aria-label="Close transfer dialog"
                onClick={closeTransferDialog}
              />

              <div className="card shadow-lg border-0 rounded-4 position-relative w-100" style={{ maxWidth: '44rem' }}>
                <div className="card-header bg-white border-0 pt-4 px-4 px-lg-4 pb-0 d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div className="text-uppercase text-body-secondary small fw-semibold">Fund Transfer - FedWire pretend transfer</div>
                    <h2 className="h4 fw-bold mb-0 mt-1">Add Funds</h2>
                    <div className="small text-muted mt-1">This form simulates a FedWire transfer by allowing you to transfer funds from the default sender bank (with RTN 090000515) to any receiver bank registered in the system. Note that this does not actually initiate a real FedWire transfer. Your bank will be allowed to use ACH until hitting its net debit cap, after that the system will notify the bank, and restrict the bank from sending more ACH transactions until the balance is back under the net debit cap. This form allows you to simulate incoming funds to a bank.</div>
                    <div className="small text-muted">For FedWire one of the banks must be a registered bank.</div>
                  </div>
                  <button type="button" className="btn-close" aria-label="Close" onClick={closeTransferDialog} />
                </div>

                <form onSubmit={submitTransferForm}>
                  <div className="card-body p-4 p-lg-4">
                    <div className="row g-3">
                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="transfer-sender-rtn">
                          Sender RTN
                        </label>
                        <input
                          id="transfer-sender-rtn"
                          className="form-control"
                          type="text"
                          value={transferForm.sender_master_account_rtn}
                          disabled
                          required
                        />
                        <small className="text-muted">Default: 090000515</small>
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="transfer-receiver-rtn">
                          Receiver RTN
                        </label>
                        <input
                          id="transfer-receiver-rtn"
                          className="form-control"
                          type="text"
                          value={transferForm.receiver_master_account_rtn}
                          disabled
                          required
                        />
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="transfer-amount">
                          Amount (in cents)
                        </label>
                        <input
                          id="transfer-amount"
                          className="form-control"
                          type="number"
                          min="1"
                          step="1"
                          value={transferForm.amount_cents}
                          onChange={(event) => updateTransferForm('amount_cents', event.target.value)}
                          disabled={transferSubmitting}
                          required
                        />
                      </div>

                      <div className="col-12 col-md-6">
                        <label className="form-label fw-semibold" htmlFor="transfer-rail">
                          Rail Type
                        </label>
                        <input
                          id="transfer-rail"
                          className="form-control"
                          type="text"
                          value={transferForm.rail_type}
                          disabled
                          required
                        />
                        <small className="text-muted">Fixed to FedWire</small>
                      </div>

                      <div className="col-12">
                        <label className="form-label fw-semibold" htmlFor="transfer-ref-id">
                          External Reference ID (optional)
                        </label>
                        <input
                          id="transfer-ref-id"
                          className="form-control"
                          type="text"
                          value={transferForm.external_ref_id}
                          onChange={(event) => updateTransferForm('external_ref_id', event.target.value)}
                          disabled={transferSubmitting}
                        />
                      </div>

                      <div className="col-12">
                        <label className="form-label fw-semibold" htmlFor="transfer-effective-date">
                          Effective Date (optional)
                        </label>
                        <input
                          id="transfer-effective-date"
                          className="form-control"
                          type="date"
                          value={transferForm.effective_date}
                          onChange={(event) => updateTransferForm('effective_date', event.target.value)}
                          disabled={transferSubmitting}
                        />
                      </div>
                    </div>

                    {transferError ? <div className="alert alert-danger mt-3 mb-0">{transferError}</div> : null}
                  </div>

                  <div className="card-footer bg-white border-0 px-4 pb-4 pt-0 d-flex flex-column flex-sm-row justify-content-end gap-2">
                    <button type="button" className="btn btn-outline-secondary" onClick={closeTransferDialog} disabled={transferSubmitting}>
                      Cancel
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={transferSubmitting}>
                      {transferSubmitting ? 'Transferring...' : 'Transfer'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          ) : null}
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

  const loadAchBanks = () => {
    if (page !== pages.home) {
      return
    }

    setAchBanksLoading(true)
    fetch(`${apiUrl}/api/ach-banks`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => setAchBanks(data.banks || []))
      .catch(() => setAchBanks([]))
      .finally(() => setAchBanksLoading(false))
  }

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

    loadAchBanks()
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
        onBankAdded={loadAchBanks}
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
