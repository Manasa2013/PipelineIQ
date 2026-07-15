import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listPendingApprovals, approveDraft, rejectDraft } from '../api';

export default function PendingApprovals() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionId, setActionId] = useState(null);
  const [msg, setMsg] = useState(null);

  const fetchPending = () => {
    setLoading(true);
    listPendingApprovals()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(fetchPending, []);

  const handleApprove = async (leadId) => {
    setActionId(leadId);
    setMsg(null);
    try {
      const result = await approveDraft(leadId, { approved_by: 'admin@example.com' });
      setMsg({ type: 'success', text: `Approved — ${result.status_label}` });
      fetchPending();
    } catch (err) {
      setMsg({ type: 'error', text: err.body?.detail || err.message });
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async (leadId) => {
    const reason = prompt('Reason for rejection (optional):');
    setActionId(leadId);
    setMsg(null);
    try {
      const result = await rejectDraft(leadId, {
        approved_by: 'admin@example.com',
        reason: reason || undefined,
      });
      setMsg({ type: 'success', text: `Rejected — ${result.status_label}` });
      fetchPending();
    } catch (err) {
      setMsg({ type: 'error', text: err.body?.detail || err.message });
    } finally {
      setActionId(null);
    }
  };

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }

  return (
    <div>
      <div className="page-header">
        <h1>Pending Approvals</h1>
        <p>Leads awaiting human review before sending</p>
      </div>

      {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

      {data && data.pending.length === 0 ? (
        <div className="empty-state">
          <div className="icon">&#9989;</div>
          <h3>No pending approvals</h3>
          <p>All leads have been reviewed or drafts are still being generated.</p>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Company</th>
                  <th>Score</th>
                  <th>Classification</th>
                  <th>Draft Subject</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.pending.map((item) => (
                  <tr key={item.lead_id}>
                    <td>
                      <a
                        href="#"
                        onClick={(e) => { e.preventDefault(); navigate(`/lead/${item.lead_id}`); }}
                        style={{ fontWeight: 600 }}
                      >
                        {item.lead_name}
                      </a>
                    </td>
                    <td>{item.lead_company}</td>
                    <td>{item.score != null ? `${item.score}/100` : '—'}</td>
                    <td>
                      {item.classification ? (
                        <span className={`badge ${item.classification === 'hot' ? 'badge-hot' : item.classification === 'nurture' ? 'badge-nurture' : 'badge-disqualify'}`}>
                          {item.classification}
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.draft_subject}
                    </td>
                    <td>
                      <span className={`badge ${item.draft_status === 'draft' ? 'badge-warning' : 'badge-success'}`}>
                        {item.draft_status}
                      </span>
                    </td>
                    <td>
                      <div className="approval-actions">
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handleApprove(item.lead_id)}
                          disabled={actionId === item.lead_id}
                        >
                          Approve
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleReject(item.lead_id)}
                          disabled={actionId === item.lead_id}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}