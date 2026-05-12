import React, { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [banks, setBanks] = useState({})
  const [transactions, setTransactions] = useState([])
  const [queue, setQueue] = useState([])
  const [reports, setReports] = useState([]) 
  const [activeTab, setActiveTab] = useState('operator')
  const [timeFilter, setTimeFilter] = useState('today')
  const [currentPage, setCurrentPage] = useState(1)
  const [injectBank, setInjectBank] = useState('')
  const [injectAmount, setInjectAmount] = useState(10000)
  const [msg, setMsg] = useState('')
  const itemsPerPage = 8

  const fetchData = async () => {
    try {
      const [rB, rT, rQ, rR] = await Promise.all([
        fetch('http://localhost:8000/banks'), 
        fetch('http://localhost:8000/transactions'), 
        fetch('http://localhost:8000/queue'),
        fetch('http://localhost:8000/netting-reports') 
      ])
      
      if (rB.ok) { 
        const d = await rB.json()
        setBanks(d)
        setInjectBank(prev => prev || Object.keys(d).sort()[0] || '')
      }
      if (rT.ok) setTransactions(await rT.json())
      if (rQ.ok) setQueue(await rQ.json())
      if (rR.ok) setReports(await rR.json()) 
    } catch { console.error("API Error") }
  }

  useEffect(() => { 
    fetchData()
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [])

  const act = async (url, method = 'POST', body = null) => {
    const res = await fetch(`http://localhost:8000${url}`, { 
      method, headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : null 
    })
    const d = await res.json()
    setMsg(d.message)
    setTimeout(() => setMsg(''), 5000)
    fetchData()
  }

  const isBankView = activeTab !== 'operator';
  
  // HISTORIA TRANSAKCJI
  const filtered = transactions.filter(t => (activeTab === 'operator' || t.sender === activeTab || t.receiver === activeTab) && (timeFilter === 'today' ? new Date(t.timestamp).toDateString() === new Date().toDateString() : true))
  const paginated = filtered.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)
  const totalPages = Math.ceil(filtered.length / itemsPerPage)

  // RAPORTY
  const bankReports = reports.filter(r => activeTab === 'operator' || r.bank_code === activeTab);

  return (
    <div className="dashboard">
      <header className="main-header">
        <h1> RTP</h1>
        <nav className="nav-tabs">
          <button className={activeTab === 'operator' ? 'active' : ''} onClick={() => {setActiveTab('operator'); setCurrentPage(1)}}>Operator</button>
          {Object.keys(banks).sort().map(c => <button key={c} className={activeTab === c ? 'active' : ''} onClick={() => {setActiveTab(c); setCurrentPage(1)}}>{c}</button>)}
        </nav>
      </header>

      {/* Alerty ograniczone do konkretengo banku lub operatora */}
      {Object.entries(banks).map(([c, b]) => (activeTab === 'operator' || activeTab === c) && (b.status === 'BLOCKED' || b.limit_exceeded_at) && (
        <div key={c} className="alert"><strong>{c}:</strong> {b.status === 'BLOCKED' ? 'INSTITUTION SUSPENDED' : 'CRITICAL LIQUIDITY WARNING (POPUP SIMULATION)'}</div>
      ))}

      <main className="content">
        {!isBankView ? (
          /* WIDOK OPERATORA */
          <div className="card">
            <h2>Network Participants Status {msg && <small className="toast">- {msg}</small>}</h2>
            <table className="table">
              <thead><tr><th>ID</th><th>Status</th><th>Balance</th><th>Limit</th><th>Liquidity</th><th>Action</th></tr></thead>
              <tbody>{Object.entries(banks).map(([c, b]) => (
                <tr key={c} className={b.status === 'BLOCKED' ? 'red-row' : ''}>
                  <td><b>{c}</b></td><td>{b.status}</td>
                  <td className={b.balance < 0 ? 'red' : 'green'}>${b.balance.toFixed(2)}</td>
                  <td>${b.debt_limit}</td><td><b>${(b.balance + b.debt_limit).toFixed(2)}</b></td>
                  <td><button className="btn" onClick={() => act(`/banks/${c}/status`, 'PATCH', {status: b.status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE'})}>{b.status === 'ACTIVE' ? 'Block' : 'Restore'}</button></td>
                </tr>
              ))}</tbody>
            </table>
            <div className="toolbar">
              <button className="btn netting" onClick={() => act('/gridlock-resolve')}>Netting Engine</button>
              <div className="inject-box">
                <select value={injectBank} onChange={e => setInjectBank(e.target.value)}>{Object.keys(banks).map(c => <option key={c} value={c}>{c}</option>)}</select>
                <input type="number" value={injectAmount} onChange={e => setInjectAmount(e.target.value)} />
                <button className="btn green" onClick={() => act('/central-bank/inject', 'POST', {bank_code: injectBank, amount: parseFloat(injectAmount)})}>Inject</button>
              </div>
            </div>
          </div>
        ) : (
          /* WIDOK PRACOWNIKA BANKU */
          <div className={`card bank-card ${banks[activeTab]?.status}`}>
            <h2>{activeTab} - {banks[activeTab]?.status}</h2>
            <div className="stats">
              <div><p>Balance</p><h3>${banks[activeTab]?.balance.toFixed(2)}</h3></div>
              <div><p>Limit</p><h3>${banks[activeTab]?.debt_limit}</h3></div>
              <div><p>Total Liquidity</p><h3>${(banks[activeTab]?.balance + banks[activeTab]?.debt_limit).toFixed(2)}</h3></div>
            </div>
          </div>
        )}

        {/* RAPORTY Z SESJI */}
        {bankReports.length > 0 && (
          <div className="card reports-card">
            <h2>Settlement Session Reports (Feedback to Banks)</h2>
            <table className="table">
              <thead><tr><th>Session ID</th><th>Bank</th><th>Net Result</th><th>Status</th><th>Time</th></tr></thead>
              <tbody>{bankReports.map(r => (
                <tr key={r.id}>
                  <td><code>{r.session_id}</code></td>
                  <td>{r.bank_code}</td>
                  <td className={r.net_position < 0 ? 'red' : 'green'}>
                    {r.net_position < 0 ? 'OWES' : 'RECEIVES'} ${Math.abs(r.net_position).toFixed(2)}
                  </td>
                  <td><span className="badge">{r.status}</span></td>
                  <td className="dim">{new Date(r.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}

        {/* HISTORIA TRANSAKCJI */}
        <div className="card">
          <div className="card-header">
            <h2> Transaction History</h2>
            <div className="filters">
              <button className={timeFilter === 'today' ? 'active' : ''} onClick={() => {setTimeFilter('today'); setCurrentPage(1)}}>Today</button>
              <button className={timeFilter === 'month' ? 'active' : ''} onClick={() => {setTimeFilter('month'); setCurrentPage(1)}}>30 Days</button>
            </div>
          </div>
          <table className="table">
            <thead>
              <tr><th>Time</th><th>From</th><th>To</th><th>Amount</th><th>Type</th></tr>
            </thead>
            <tbody>
              {paginated.map(t => (
                <tr key={t.id}>
                  <td>{new Date(t.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}</td>
                  <td>{t.sender}</td>
                  <td>{t.receiver}</td>
                  <td className={t.sender === activeTab ? 'red' : 'green'}>${t.amount.toFixed(2)}</td>
                  <td>{t.status}</td>
                </tr>
              ))}
              {paginated.length === 0 && <tr><td colSpan="5">No transactions found.</td></tr>}
            </tbody>
          </table>
          
          <div className="pager">
            <button disabled={currentPage === 1} onClick={() => setCurrentPage(p => p - 1)}>Prev</button>
            <span>{currentPage} / {totalPages || 1}</span>
            <button disabled={currentPage === totalPages || totalPages === 0} onClick={() => setCurrentPage(p => p + 1)}>Next</button>
          </div>
        </div>

      </main>
    </div>
  )
}

export default App