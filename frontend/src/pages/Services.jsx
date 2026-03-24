import { useState, useEffect } from 'react';
import { getServices, addService, deleteService, updateService } from '../api';

function Services() {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '', source_type: 'k8s_pod', namespace: '', label_selector: '', log_path: '', git_repo: '',
  });

  const fetchServices = async () => {
    try {
      const res = await getServices();
      setServices(res.data);
    } catch (err) {
      console.error('Failed to fetch services:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchServices(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await addService(form);
      setShowForm(false);
      setForm({ name: '', source_type: 'k8s_pod', namespace: '', label_selector: '', log_path: '', git_repo: '' });
      fetchServices();
    } catch (err) {
      console.error('Failed to add service:', err);
    }
  };

  const handleToggle = async (svc) => {
    try {
      await updateService(svc.id, { enabled: !svc.enabled });
      fetchServices();
    } catch (err) {
      console.error('Failed to toggle service:', err);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this service?')) return;
    try {
      await deleteService(id);
      fetchServices();
    } catch (err) {
      console.error('Failed to delete service:', err);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Monitored Services</h1>
        <button className="btn primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ Add Service'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3>Add Service</h3>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label>Name</label>
                <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
              </div>
              <div className="form-group">
                <label>Source Type</label>
                <select value={form.source_type} onChange={e => setForm({ ...form, source_type: e.target.value })}>
                  <option value="k8s_pod">K8s Pod</option>
                  <option value="remote_file">Remote File</option>
                </select>
              </div>
              {form.source_type === 'k8s_pod' && (
                <>
                  <div className="form-group">
                    <label>Namespace</label>
                    <input value={form.namespace} onChange={e => setForm({ ...form, namespace: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Label Selector</label>
                    <input value={form.label_selector} onChange={e => setForm({ ...form, label_selector: e.target.value })} placeholder="app=data-pipeline" />
                  </div>
                </>
              )}
              {form.source_type === 'remote_file' && (
                <div className="form-group">
                  <label>Log Path</label>
                  <input value={form.log_path} onChange={e => setForm({ ...form, log_path: e.target.value })} />
                </div>
              )}
              <div className="form-group">
                <label>Git Repo</label>
                <input value={form.git_repo} onChange={e => setForm({ ...form, git_repo: e.target.value })} />
              </div>
            </div>
            <button type="submit" className="btn primary" style={{ marginTop: 12 }}>Save</button>
          </form>
        </div>
      )}

      <div className="card">
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Source Type</th>
                <th>Namespace</th>
                <th>Selector / Path</th>
                <th>Enabled</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {services.map((svc, i) => (
                <tr key={svc.id || i}>
                  <td style={{ fontWeight: 600 }}>{svc.name}</td>
                  <td><span className="badge info">{svc.source_type}</span></td>
                  <td>{svc.namespace || '-'}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {svc.label_selector || svc.log_path || '-'}
                  </td>
                  <td>
                    <span
                      className={`badge ${svc.enabled ? 'success' : 'warning'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleToggle(svc)}
                    >
                      {svc.enabled ? 'ON' : 'OFF'}
                    </span>
                  </td>
                  <td>
                    <button className="btn danger" style={{ padding: '4px 10px', fontSize: 11 }} onClick={() => handleDelete(svc.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {services.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: '#8b949e' }}>No services configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Services;
