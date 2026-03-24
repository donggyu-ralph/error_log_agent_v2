import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { getSummary, getTimeline, getErrorsByType } from '../api';

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [byType, setByType] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [sumRes, tlRes, typeRes] = await Promise.all([
          getSummary(),
          getTimeline(7),
          getErrorsByType(7),
        ]);
        setSummary(sumRes.data);
        setTimeline(tlRes.data);
        setByType(typeRes.data);
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const navigate = useNavigate();

  if (loading) return <div className="loading">Loading...</div>;

  const recentErrors = summary?.recent_errors || [];
  const recentFixes = summary?.recent_fixes || [];
  const todayTotal = summary?.total_errors_today || 0;

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <div className="stats-grid">
        <div className="stat-card critical clickable" onClick={() => navigate('/errors')}>
          <div className="value">{todayTotal}</div>
          <div className="label">Errors Today</div>
        </div>
        <div className="stat-card warning clickable" onClick={() => navigate('/errors')}>
          <div className="value">{recentErrors.length}</div>
          <div className="label">Recent Errors</div>
        </div>
        <div className="stat-card success clickable" onClick={() => navigate('/history')}>
          <div className="value">{recentFixes.length}</div>
          <div className="label">Recent Fixes</div>
        </div>
        <div className="stat-card info clickable" onClick={() => navigate('/errors')}>
          <div className="value">{byType.length}</div>
          <div className="label">Error Types</div>
        </div>
      </div>

      <div className="charts-grid">
        <div className="card">
          <h3>Error Timeline (7 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={timeline.map(t => ({ ...t, label: `${t.date} ${String(t.hour).padStart(2, '0')}:00` }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="label" stroke="#8b949e" fontSize={11} />
              <YAxis stroke="#8b949e" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e1e4e8' }}
                labelStyle={{ color: '#8b949e' }}
                formatter={(value) => [`${value} errors`, 'Count']}
              />
              <Line type="monotone" dataKey="total" stroke="#f85149" strokeWidth={2} dot={{ r: 4, fill: '#f85149' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>Errors by Type</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={byType.slice(0, 8)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis type="number" stroke="#8b949e" fontSize={11} />
              <YAxis dataKey="error_type" type="category" stroke="#8b949e" fontSize={10} width={120} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
              />
              <Bar dataKey="total" fill="#58a6ff" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h3>Recent Errors</h3>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Service</th>
                <th>Level</th>
                <th>Type</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {recentErrors.map((err, i) => (
                <tr key={i}>
                  <td>{new Date(err.timestamp).toLocaleString()}</td>
                  <td>{err.service_name}</td>
                  <td><span className={`badge ${err.level?.toLowerCase()}`}>{err.level}</span></td>
                  <td>{err.error_type || '-'}</td>
                  <td style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <Link to={`/errors/${err.id}`} style={{ color: '#58a6ff', textDecoration: 'none' }}>
                      {err.message}
                    </Link>
                  </td>
                </tr>
              ))}
              {recentErrors.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: '#8b949e' }}>No errors detected</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
