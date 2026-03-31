import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getServiceDetail, inviteMember, removeMember } from '../api';

function ServiceDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [service, setService] = useState(null);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchService = async () => {
    try {
      const res = await getServiceDetail(id);
      setService(res.data);
    } catch (err) {
      console.error('Failed to fetch service:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchService(); }, [id]);

  if (loading) return <div className="loading">Loading...</div>;
  if (!service) return <div className="empty">Service not found</div>;

  const isOwner = service.members?.some(m => m.user_id === user?.id && m.role === 'owner');
  const isAdmin = user?.role === 'admin';
  const canManage = isOwner || isAdmin;

  const handleInvite = async (e) => {
    e.preventDefault();
    setError(''); setSuccess('');
    try {
      await inviteMember(id, inviteEmail);
      setSuccess(`${inviteEmail} 초대 완료`);
      setInviteEmail('');
      fetchService();
    } catch (err) {
      setError(err.response?.data?.detail || 'Invite failed');
    }
  };

  const handleRemove = async (userId, email) => {
    if (!confirm(`${email}을(를) 멤버에서 제거하시겠습니까?`)) return;
    try {
      await removeMember(id, userId);
      fetchService();
    } catch (err) {
      setError(err.response?.data?.detail || 'Remove failed');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>{service.name}</h1>
        <Link to="/services" className="btn">Back</Link>
      </div>

      {/* Service Info */}
      <div className="card">
        <h3>Service Info</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="detail-section">
            <h4>Source Type</h4>
            <span className="badge info">{service.source_type}</span>
          </div>
          <div className="detail-section">
            <h4>Status</h4>
            <span className={`badge ${service.enabled ? 'success' : 'warning'}`}>
              {service.enabled ? 'Active' : 'Disabled'}
            </span>
          </div>
          {service.namespace && (
            <div className="detail-section">
              <h4>Namespace</h4>
              <p>{service.namespace}</p>
            </div>
          )}
          {service.label_selector && (
            <div className="detail-section">
              <h4>Label Selector</h4>
              <code>{service.label_selector}</code>
            </div>
          )}
          {service.slack_channel_id && (
            <div className="detail-section">
              <h4>Slack Channel</h4>
              <code>{service.slack_channel_id}</code>
            </div>
          )}
        </div>
      </div>

      {/* Members */}
      <div className="card">
        <h3>Members ({service.members?.length || 0})</h3>

        {canManage && (
          <form onSubmit={handleInvite} style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              placeholder="이메일로 초대"
              style={{ flex: 1, padding: '8px 12px', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9' }}
              required
            />
            <button type="submit" className="btn primary">초대</button>
          </form>
        )}

        {error && <div style={{ color: '#f85149', marginBottom: 8, fontSize: 13 }}>{error}</div>}
        {success && <div style={{ color: '#3fb950', marginBottom: 8, fontSize: 13 }}>{success}</div>}

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Joined</th>
                {canManage && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {(service.members || []).map((m, i) => (
                <tr key={m.user_id || i}>
                  <td>{m.email}</td>
                  <td>
                    <span className={`badge ${m.role === 'owner' ? 'error' : 'info'}`}>
                      {m.role}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: '#8b949e' }}>
                    {m.created_at ? new Date(m.created_at).toLocaleDateString() : '-'}
                  </td>
                  {canManage && (
                    <td>
                      {m.role !== 'owner' && m.user_id !== user?.id && (
                        <button
                          className="btn danger"
                          style={{ padding: '4px 10px', fontSize: 11 }}
                          onClick={() => handleRemove(m.user_id, m.email)}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ServiceDetail;
