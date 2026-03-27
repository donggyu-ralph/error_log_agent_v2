import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('비밀번호가 일치하지 않습니다');
      return;
    }
    try {
      await register(email, password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#0f1117' }}>
      <div className="card" style={{ width: 400, padding: 32 }}>
        <h2 style={{ textAlign: 'center', marginBottom: 24, color: '#58a6ff' }}>회원가입</h2>
        <form onSubmit={handleSubmit}>
          {error && <div style={{ color: '#f85149', marginBottom: 12, fontSize: 13 }}>{error}</div>}
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
          </div>
          <div className="form-group">
            <label>Confirm Password</label>
            <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required />
          </div>
          <button type="submit" className="btn primary" style={{ width: '100%', marginTop: 8 }}>Register</button>
        </form>
        <p style={{ textAlign: 'center', marginTop: 16, color: '#8b949e', fontSize: 13 }}>
          이미 계정이 있으신가요? <Link to="/login" style={{ color: '#58a6ff' }}>로그인</Link>
        </p>
      </div>
    </div>
  );
}

export default Register;
