import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#0f1117' }}>
      <div className="card" style={{ width: 400, padding: 32 }}>
        <h2 style={{ textAlign: 'center', marginBottom: 24, color: '#58a6ff' }}>Error Log Agent</h2>
        <form onSubmit={handleSubmit}>
          {error && <div style={{ color: '#f85149', marginBottom: 12, fontSize: 13 }}>{error}</div>}
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <button type="submit" className="btn primary" style={{ width: '100%', marginTop: 8 }}>Login</button>
        </form>
        <p style={{ textAlign: 'center', marginTop: 16, color: '#8b949e', fontSize: 13 }}>
          계정이 없으신가요? <Link to="/register" style={{ color: '#58a6ff' }}>회원가입</Link>
        </p>
      </div>
    </div>
  );
}

export default Login;
