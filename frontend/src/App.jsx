import { BrowserRouter as Router, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Dashboard from './pages/Dashboard';
import ErrorList from './pages/ErrorList';
import ErrorDetail from './pages/ErrorDetail';
import FixHistory from './pages/FixHistory';
import Services from './pages/Services';
import Login from './pages/Login';
import Register from './pages/Register';
import './App.css';

function AppLayout() {
  const { user, logout, isAdmin } = useAuth();

  if (!user) return <Navigate to="/login" />;

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-header">
          <h2>Error Log Agent</h2>
          <span className="version">v2.0</span>
        </div>
        <ul>
          <li><NavLink to="/" end>Dashboard</NavLink></li>
          <li><NavLink to="/errors">Error Logs</NavLink></li>
          <li><NavLink to="/history">Fix History</NavLink></li>
          <li><NavLink to="/services">Services</NavLink></li>
        </ul>
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="user-email">{user.email}</span>
            <span className={`badge ${user.role === 'admin' ? 'error' : user.role === 'operator' ? 'info' : 'success'}`}>
              {user.role}
            </span>
          </div>
          <button className="btn" onClick={logout} style={{ width: '100%', marginTop: 8, fontSize: 12 }}>
            Logout
          </button>
        </div>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/errors" element={<ErrorList />} />
          <Route path="/errors/:id" element={<ErrorDetail />} />
          <Route path="/history" element={<FixHistory />} />
          <Route path="/services" element={<Services />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          } />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
