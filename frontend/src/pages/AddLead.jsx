import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createLead } from '../api';

export default function AddLead() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: '',
    email: '',
    company: '',
    role: '',
    industry: '',
    buying_signals: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const signals = form.buying_signals
        ? form.buying_signals.split(',').map((s) => s.trim()).filter(Boolean)
        : [];

      const result = await createLead({
        name: form.name,
        email: form.email,
        company: form.company,
        role: form.role || undefined,
        industry: form.industry || undefined,
        buying_signals: signals.length > 0 ? signals : undefined,
      });

      setSuccess(`Lead "${result.name}" created successfully!`);
      setForm({ name: '', email: '', company: '', role: '', industry: '', buying_signals: '' });

      setTimeout(() => navigate(`/lead/${result.id}`), 1500);
    } catch (err) {
      // err.message is already a plain string (normalised in api.js).
      // Guard against any edge-case where a raw object slips through.
      const raw = err.message || err.body?.detail;
      if (typeof raw === 'string') {
        setError(raw);
      } else if (Array.isArray(raw)) {
        setError(raw.map((e) => e.msg || JSON.stringify(e)).join('; '));
      } else if (raw && typeof raw === 'object') {
        setError(JSON.stringify(raw));
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Add Lead</h1>
        <p>Create a new lead in the pipeline</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="card" style={{ maxWidth: 640 }}>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>Name *</label>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder="Jane Doe"
                required
              />
            </div>
            <div className="form-group">
              <label>Email *</label>
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                placeholder="jane@acme.com"
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Company *</label>
              <input
                name="company"
                value={form.company}
                onChange={handleChange}
                placeholder="Acme Corp"
                required
              />
            </div>
            <div className="form-group">
              <label>Role</label>
              <input
                name="role"
                value={form.role}
                onChange={handleChange}
                placeholder="CTO"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Industry</label>
              <input
                name="industry"
                value={form.industry}
                onChange={handleChange}
                placeholder="SaaS"
              />
            </div>
            <div className="form-group">
              <label>Buying Signals (comma-separated)</label>
              <input
                name="buying_signals"
                value={form.buying_signals}
                onChange={handleChange}
                placeholder="visited pricing page, requested demo"
              />
            </div>
          </div>

          <div className="btn-group" style={{ marginTop: '1rem' }}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Lead'}
            </button>
            <button type="button" className="btn btn-outline" onClick={() => navigate('/')}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}