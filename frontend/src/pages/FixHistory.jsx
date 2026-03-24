import { useState, useEffect } from 'react';
import { getHistory } from '../api';

function FixHistory() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHistory() {
      try {
        const res = await getHistory({ limit: 50 });
        setHistory(res.data);
      } catch (err) {
        console.error('Failed to fetch history:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchHistory();
  }, []);

  if (loading) return <div className="loading">Loading...</div>;

  const statusBadge = (h) => {
    if (h.production_deployed) return <span className="badge success">Deployed</span>;
    if (h.staging_result === 'healthy') return <span className="badge info">Staging OK</span>;
    if (h.action === 'reject') return <span className="badge warning">Rejected</span>;
    return <span className="badge error">Failed</span>;
  };

  return (
    <div>
      <div className="page-header">
        <h1>Fix History</h1>
      </div>

      <div className="card">
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Thread</th>
                <th>Action</th>
                <th>Git Branch</th>
                <th>Image</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={h.id || i}>
                  <td style={{ whiteSpace: 'nowrap' }}>{new Date(h.created_at).toLocaleString()}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{h.thread_id?.slice(0, 8) || '-'}</td>
                  <td>{h.action || '-'}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{h.git_branch || '-'}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {h.harbor_image || '-'}
                  </td>
                  <td>{statusBadge(h)}</td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: '#8b949e' }}>No fix history</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default FixHistory;
