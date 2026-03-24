import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getErrors } from '../api';

const PAGE_SIZE = 20;

function ErrorList() {
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    async function fetchErrors() {
      setLoading(true);
      try {
        const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE };
        if (filter) params.service_name = filter;
        const res = await getErrors(params);
        setErrors(res.data);
        setTotal(res.data.length);
      } catch (err) {
        console.error('Failed to fetch errors:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchErrors();
  }, [filter, page]);

  if (loading && page === 0) return <div className="loading">Loading...</div>;

  const services = [...new Set(errors.map(e => e.service_name).filter(Boolean))];

  return (
    <div>
      <div className="page-header">
        <h1>Error Logs</h1>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <select
            value={filter}
            onChange={e => { setFilter(e.target.value); setPage(0); }}
            style={{ padding: '6px 12px', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9' }}
          >
            <option value="">All Services</option>
            {services.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="card">
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Service</th>
                <th>Level</th>
                <th>Type</th>
                <th>Message</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((err, i) => (
                <tr key={err.id || i}>
                  <td style={{ whiteSpace: 'nowrap' }}>{new Date(err.timestamp).toLocaleString()}</td>
                  <td>{err.service_name}</td>
                  <td><span className={`badge ${err.level?.toLowerCase()}`}>{err.level}</span></td>
                  <td>{err.error_type || '알 수 없음'}</td>
                  <td style={{ maxWidth: 350, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <Link to={`/errors/${err.id}`} style={{ color: '#58a6ff', textDecoration: 'none' }}>
                      {err.message}
                    </Link>
                  </td>
                  <td><span className="badge info">{err.source}</span></td>
                </tr>
              ))}
              {errors.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: '#8b949e' }}>No errors found</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="pagination">
          <button className="btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
            Previous
          </button>
          <span className="page-info">Page {page + 1}</span>
          <button className="btn" disabled={total < PAGE_SIZE} onClick={() => setPage(p => p + 1)}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export default ErrorList;
