import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getErrorById } from '../api';

function ErrorDetail() {
  const { id } = useParams();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchError() {
      try {
        const res = await getErrorById(id);
        setError(res.data);
      } catch (err) {
        console.error('Failed to fetch error:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchError();
  }, [id]);

  if (loading) return <div className="loading">Loading...</div>;
  if (!error) return <div className="empty">Error not found</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Error Detail</h1>
        <Link to="/errors" className="btn">Back to List</Link>
      </div>

      <div className="card">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div className="detail-section">
            <h4>Service</h4>
            <p>{error.service_name || '-'}</p>
          </div>
          <div className="detail-section">
            <h4>Timestamp</h4>
            <p>{new Date(error.timestamp).toLocaleString()}</p>
          </div>
          <div className="detail-section">
            <h4>Level</h4>
            <span className={`badge ${error.level?.toLowerCase()}`}>{error.level}</span>
          </div>
          <div className="detail-section">
            <h4>Error Type</h4>
            <p>{error.error_type || '-'}</p>
          </div>
          <div className="detail-section">
            <h4>Source</h4>
            <span className="badge info">{error.source}</span>
            {error.pod_name && <span style={{ marginLeft: 8, color: '#8b949e' }}>{error.pod_name}</span>}
          </div>
          <div className="detail-section">
            <h4>Location</h4>
            <p>{error.file_path ? `${error.file_path}:${error.line_number || '?'}` : '-'}</p>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Error Message</h3>
        <pre className="code-block">{error.message}</pre>
      </div>

      {error.traceback && (
        <div className="card">
          <h3>Traceback</h3>
          <pre className="code-block">{error.traceback}</pre>
        </div>
      )}
    </div>
  );
}

export default ErrorDetail;
