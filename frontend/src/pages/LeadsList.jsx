import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listLeads } from '../api';

const CLASS_BADGE = {
  hot: 'badge-hot',
  nurture: 'badge-nurture',
  disqualify: 'badge-disqualify',
};

export default function LeadsList() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');

  const fetchLeads = () => {
    setLoading(true);
    listLeads({ search: search || undefined, sort_by: sortBy, sort_order: sortOrder, limit: 100 })
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(fetchLeads, [sortBy, sortOrder]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchLeads();
  };

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Leads</h1>
          <p>All leads in the pipeline</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/add-lead')}>
          + Add Lead
        </button>
      </div>

      <div className="search-bar">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', flex: 1 }}>
          <input
            placeholder="Search by name, email, or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="btn btn-primary btn-sm">Search</button>
        </form>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="created_at">Created</option>
          <option value="name">Name</option>
          <option value="email">Email</option>
          <option value="company">Company</option>
        </select>
        <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
          <option value="desc">Desc</option>
          <option value="asc">Asc</option>
        </select>
      </div>

      {loading && (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      {data && data.leads.length === 0 ? (
        <div className="empty-state">
          <div className="icon">&#128270;</div>
          <h3>No leads found</h3>
          <p>{search ? 'Try a different search term.' : 'Add your first lead to get started.'}</p>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Industry</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data?.leads.map((lead) => (
                  <tr
                    key={lead.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/lead/${lead.id}`)}
                  >
                    <td style={{ fontWeight: 600 }}>{lead.name}</td>
                    <td>{lead.email}</td>
                    <td>{lead.company}</td>
                    <td>{lead.role || '—'}</td>
                    <td>{lead.industry || '—'}</td>
                    <td>{new Date(lead.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && (
            <div className="pagination">
              <span>Showing {data.leads.length} of {data.total} leads</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}