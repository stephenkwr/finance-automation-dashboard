import { useState } from 'react'
import './App.css'

function App() {
  const [result, setResult] = useState("Click the button to ping the backend...")
  const [loading, setLoading] = useState(false)

  async function pingBackend(){
    setLoading(true);
    try{
      const res = await fetch("http://localhost:8000/api/ping");
      const data = await res.json();
      setResult(JSON.stringify(data));
    } catch (err){
      setResult("Error: " + err.message);
    }finally{
      setLoading(false);
    }
  }
  return (
    <div style={{ padding: 24, fontFamily: "sans-serif"}}>
      <h1>Finance Automation Dashboard</h1>
        
      <button onClick={pingBackend} disabled={loading}>
        {loading ? "Pinging..." : "Ping API"}
      </button>
  
      <pre style={{ marginTop:16, background: "#f4f4f4", color: "black", padding: 12}}>
        {result}
      </pre>
    </div>
  );
}
export default App



