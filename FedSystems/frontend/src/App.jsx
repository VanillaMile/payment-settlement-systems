import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [backendStatus, setBackendStatus] = useState('Loading...')
  const [apiUrl] = useState(() => {
    const port = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001'
    return port
  })

  useEffect(() => {
    // Test connection to backend
    fetch(`${apiUrl}/health`)
      .then(res => res.json())
      .then(data => setBackendStatus(`Backend OK: ${JSON.stringify(data)}`))
      .catch(err => setBackendStatus(`Backend Error: ${err.message}`))
  }, [apiUrl])

  return (
    <div className="App">
      <h1>Fed Systems Dashboard</h1>
      <section>
        <h2>ACH Processing System</h2>
        <p>API: {apiUrl}</p>
        <p>Status: {backendStatus}</p>
      </section>
    </div>
  )
}

export default App
