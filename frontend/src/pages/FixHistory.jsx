import { useState, useEffect } from 'react';
import { getHistory } from '../api';

function FixHistory() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

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

  const handleRowClick = (h) => {
    setSelected(selected?.id === h.id ? null : h);
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
                <tr
                  key={h.id || i}
                  onClick={() => handleRowClick(h)}
                  style={{ cursor: 'pointer', background: selected?.id === h.id ? '#1c2128' : undefined }}
                >
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

      {selected && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Fix Detail — {selected.thread_id?.slice(0, 8) || 'N/A'}</h3>

          {/* Analysis */}
          <div className="detail-section">
            <h4>Analysis</h4>
            {selected.analysis ? (
              <pre className="code-block">{typeof selected.analysis === 'string' ? selected.analysis : JSON.stringify(selected.analysis, null, 2)}</pre>
            ) : (
              <p style={{ color: '#8b949e', fontSize: 13 }}>분석 데이터 없음</p>
            )}
          </div>

          {/* Fix Plan */}
          <div className="detail-section">
            <h4>Fix Plan</h4>
            {selected.fix_plan ? (
              <div>
                {(() => {
                  const plan = typeof selected.fix_plan === 'string'
                    ? (() => { try { return JSON.parse(selected.fix_plan); } catch { return null; } })()
                    : selected.fix_plan;

                  if (!plan) {
                    return <pre className="code-block">{selected.fix_plan}</pre>;
                  }

                  return (
                    <div>
                      {plan.target_files && plan.target_files.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ color: '#8b949e', fontSize: 12 }}>Target Files:</span>
                          <div style={{ marginTop: 4 }}>
                            {plan.target_files.map((f, i) => (
                              <span key={i} className="badge info" style={{ marginRight: 6, marginBottom: 4 }}>{f}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {plan.description && (
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ color: '#8b949e', fontSize: 12 }}>Description:</span>
                          <p style={{ color: '#c9d1d9', fontSize: 13, marginTop: 4 }}>{plan.description}</p>
                        </div>
                      )}
                      {plan.changes && (
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ color: '#8b949e', fontSize: 12 }}>Changes:</span>
                          <pre className="code-block">{typeof plan.changes === 'string' ? plan.changes : JSON.stringify(plan.changes, null, 2)}</pre>
                        </div>
                      )}
                      {plan.diff && (
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ color: '#8b949e', fontSize: 12 }}>Diff Preview:</span>
                          <pre className="code-block">{plan.diff}</pre>
                        </div>
                      )}
                      {!plan.target_files && !plan.description && !plan.changes && !plan.diff && (
                        <pre className="code-block">{JSON.stringify(plan, null, 2)}</pre>
                      )}
                    </div>
                  );
                })()}
              </div>
            ) : (
              <p style={{ color: '#8b949e', fontSize: 13 }}>수정 계획 없음</p>
            )}
          </div>

          {/* Git & Deployment Info */}
          <div className="detail-section">
            <h4>Git & Deployment</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Branch:</span>
                <div style={{ fontFamily: 'monospace', fontSize: 13, color: '#c9d1d9', marginTop: 2 }}>
                  {selected.git_branch || '-'}
                </div>
              </div>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Commit:</span>
                <div style={{ fontFamily: 'monospace', fontSize: 13, color: '#c9d1d9', marginTop: 2 }}>
                  {selected.git_commit?.slice(0, 12) || selected.commit_sha?.slice(0, 12) || '-'}
                </div>
              </div>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Harbor Image:</span>
                <div style={{ fontFamily: 'monospace', fontSize: 12, color: '#c9d1d9', marginTop: 2, wordBreak: 'break-all' }}>
                  {selected.harbor_image || '-'}
                </div>
              </div>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Action:</span>
                <div style={{ marginTop: 2 }}>
                  <span className={`badge ${selected.action === 'approve' ? 'success' : selected.action === 'reject' ? 'warning' : 'info'}`}>
                    {selected.action || '-'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Staging & Production Status */}
          <div className="detail-section">
            <h4>Deployment Status</h4>
            <div style={{ display: 'flex', gap: 24 }}>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Staging Result:</span>
                <div style={{ marginTop: 4 }}>
                  {selected.staging_result ? (
                    <span className={`badge ${selected.staging_result === 'healthy' ? 'success' : 'error'}`}>
                      {selected.staging_result}
                    </span>
                  ) : (
                    <span style={{ color: '#8b949e', fontSize: 13 }}>-</span>
                  )}
                </div>
              </div>
              <div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>Production Deployed:</span>
                <div style={{ marginTop: 4 }}>
                  <span className={`badge ${selected.production_deployed ? 'success' : 'warning'}`}>
                    {selected.production_deployed ? 'Yes' : 'No'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Rollback info if present */}
          {selected.rollback_reason && (
            <div className="detail-section">
              <h4>Rollback Reason</h4>
              <pre className="code-block">{selected.rollback_reason}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FixHistory;
