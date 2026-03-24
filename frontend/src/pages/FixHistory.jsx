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
    if (h.action === 'approve') return <span className="badge info">In Progress</span>;
    return <span className="badge error">Pending</span>;
  };

  const handleRowClick = (h) => {
    setSelected(selected?.id === h.id ? null : h);
  };

  const parsePlan = (raw) => {
    if (!raw) return null;
    if (typeof raw === 'object') return raw;
    try { return JSON.parse(raw); } catch { return null; }
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

      {selected && (() => {
        const plan = parsePlan(selected.fix_plan);

        return (
          <div className="card" style={{ marginTop: 16 }}>
            <h3>Fix Detail — {selected.thread_id?.slice(0, 8) || 'N/A'}</h3>

            {/* Summary */}
            {plan?.summary && (
              <div className="detail-section">
                <h4>Summary</h4>
                <p style={{ color: '#c9d1d9', fontSize: 14 }}>{plan.summary}</p>
              </div>
            )}

            {/* Root Cause */}
            {plan?.root_cause && (
              <div className="detail-section">
                <h4>Root Cause</h4>
                <p style={{ color: '#c9d1d9', fontSize: 13 }}>{plan.root_cause}</p>
              </div>
            )}

            {/* Fix Description */}
            {plan?.fix_description && (
              <div className="detail-section">
                <h4>Fix Description</h4>
                <p style={{ color: '#c9d1d9', fontSize: 13 }}>{plan.fix_description}</p>
              </div>
            )}

            {/* Target Files + Diff */}
            {plan?.target_files && plan.target_files.length > 0 && (
              <div className="detail-section">
                <h4>Modified Files</h4>
                {plan.target_files.map((tf, i) => (
                  <div key={i} style={{ marginBottom: 16, padding: 12, background: '#0d1117', borderRadius: 6, border: '1px solid #30363d' }}>
                    <div style={{ marginBottom: 8 }}>
                      <span className="badge info">{typeof tf === 'string' ? tf : tf.file_path || 'unknown'}</span>
                    </div>
                    {tf.changes_description && (
                      <p style={{ color: '#8b949e', fontSize: 12, marginBottom: 8 }}>{tf.changes_description}</p>
                    )}
                    {tf.diff_preview && tf.diff_preview !== 'N/A' && (
                      <pre className="code-block" style={{ margin: 0, fontSize: 11 }}>{tf.diff_preview}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Risk */}
            {plan?.estimated_risk && (
              <div className="detail-section">
                <h4>Risk Level</h4>
                <span className={`badge ${plan.estimated_risk === 'low' ? 'success' : plan.estimated_risk === 'high' ? 'error' : 'warning'}`}>
                  {plan.estimated_risk}
                </span>
              </div>
            )}

            {/* Analysis */}
            {selected.analysis && (
              <div className="detail-section">
                <h4>LLM Analysis</h4>
                <pre className="code-block" style={{ maxHeight: 300, overflow: 'auto' }}>
                  {selected.analysis}
                </pre>
              </div>
            )}

            {/* Git & Deployment Info */}
            <div className="detail-section">
              <h4>Git & Deployment</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <span style={{ color: '#8b949e', fontSize: 12 }}>Branch:</span>
                  <div style={{ fontFamily: 'monospace', fontSize: 13, color: '#58a6ff', marginTop: 2 }}>
                    {selected.git_branch || '-'}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#8b949e', fontSize: 12 }}>Commit:</span>
                  <div style={{ fontFamily: 'monospace', fontSize: 13, color: '#c9d1d9', marginTop: 2 }}>
                    {(selected.git_commit || '-').slice(0, 12)}
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

            {/* Deployment Status */}
            <div className="detail-section">
              <h4>Deployment Status</h4>
              <div style={{ display: 'flex', gap: 24 }}>
                <div>
                  <span style={{ color: '#8b949e', fontSize: 12 }}>Staging:</span>
                  <div style={{ marginTop: 4 }}>
                    <span className={`badge ${selected.staging_result === 'healthy' ? 'success' : selected.staging_result ? 'error' : 'info'}`}>
                      {selected.staging_result || 'N/A'}
                    </span>
                  </div>
                </div>
                <div>
                  <span style={{ color: '#8b949e', fontSize: 12 }}>Production:</span>
                  <div style={{ marginTop: 4 }}>
                    <span className={`badge ${selected.production_deployed ? 'success' : 'warning'}`}>
                      {selected.production_deployed ? 'Deployed' : 'Not Deployed'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export default FixHistory;
