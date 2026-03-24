import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ErrorList from './pages/ErrorList';
import ErrorDetail from './pages/ErrorDetail';
import FixHistory from './pages/FixHistory';
import Services from './pages/Services';
import './App.css';

function App() {
  return (
    <Router>
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
    </Router>
  );
}

export default App;
