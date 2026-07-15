import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getLead, getAuditLogs, approveDraft, rejectDraft, runPipeline } from '../api';

const CLASS_BADGE = {
  hot: 'badge-hot',
  nurture: 'badge-nurture',
  disqualify: 'badge-disqualify',
};

export default function LeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [lead, setLead] = useState(null);
  const [logs, setLogs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [approving, setApproving] = useState(false);
  const [approvalMsg, setApprovalMsg] = useState(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState(null);

  useEffect(() => {
    Promise.all([
      getLead(id),
      getAuditLogs(id, { limit: 50 }),
    ])
      .then(([leadData, logsData]) => {
        setLead(leadData);
        setLogs(logsData);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleRunPipeline = async () => {
    setPipelineRunning(true);
    setPipelineMsg(null);
    try {
      await runPipeline(lead);
      setPipelineMsg({ type: 'success', text: 'Pipeline started! Refreshing...' });
      // Refresh lead data to show scores, classification, draft
      setTimeout(async () => {
        const [updatedLead, updatedLogs] = await Promise.all([
          getLead(id),
          getAuditLogs(id, { limit: 50 }),
        ]);
        setLead(updatedLead);
        setLogs(updatedLogs);
        setPipelineMsg({ type: 'success', text: 'Pipeline complete. Results updated.' });
      }, 2000);
    } catch (err) {
      setPipelineMsg({ type: 'error', text: err.body?.detail || err.message });
    } finally {
      setPipelineRunning(false);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    setApprovalMsg(null);
    try {
      const result = await approveDraft(id, { approved_by: 'admin@example.com' });
      setApprovalMsg({ type: 'success', text: `Approved! Status: ${result.status_label}` });
      // Refresh
      const updated = await getLead(id);
      setLead(updated);
    } catch (err) {
      setApprovalMsg({ type: 'error', text: err.body?.detail || err.message });
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    const reason = prompt('Reason for rejection (optional):');
    setApproving(true);
    setApprovalMsg(null);
    try {
      const result = await rejectDraft(id, {
        approved_by: 'admin@example.com',
        reason: reason || undefined,
      });
      setApprovalMsg({ type: 'success', text: `Rejected. Status: ${result.status_label}` });
      const updated = await getLead(id);
      setLead(updated);
    } catch (err) {
      setApprovalMsg({ type: 'error', text: err.body?.detail || err.message });
    } finally {
      setApproving(false);
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

  if (!lead) {
    return <div className="alert alert-warning">Lead not found.</div>;
  }

  const latestScore = lead.scores?.[lead.scores.length - 1];
  const latestClassification = lead.classifications?.[lead.classifications.length - 1];
  const latestDraft = lead.draft_emails?.[lead.draft_emails.length - 1];

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button className="btn btn-outline btn-sm" onClick={() => navigate('/leads')}>
            &larr; Back
          </button>
          <div>
            <h1>{lead.name}</h1>
            <p>{lead.email} &middot; {lead.company}</p>
          </div>
        </div>
      </div>

      {approvalMsg && (
        <div className={`alert alert-${approvalMsg.type}`}>{approvalMsg.text}</div>
      )}

      {pipelineMsg && (
        <div className={`alert alert-${pipelineMsg.type}`}>{pipelineMsg.text}</div>
      )}

      {/* Run Pipeline button — shown when lead has no score yet */}
      {!latestScore && (
        <div style={{ marginBottom: '1rem' }}>
          <button
            className="btn btn-primary"
            onClick={handleRunPipeline}
            disabled={pipelineRunning}
          >
            {pipelineRunning ? '⏳ Running AI Pipeline...' : '▶ Run AI Pipeline'}
          </button>
          <span style={{ marginLeft: '0.75rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            Qualify this lead with AI scoring, classification, and email draft generation
          </span>
        </div>
      )}

      <div className="widget-grid">
        <div className="widget">
          <div className="widget-label">Score</div>
          <div className="widget-value primary">
            {latestScore ? `${latestScore.score}/100` : '—'}
          </div>
        </div>
        <div className="widget">
          <div className="widget-label">Confidence</div>
          <div className="widget-value primary">
            {latestScore ? `${(latestScore.confidence * 100).toFixed(0)}%` : '—'}
          </div>
        </div>
        <div className="widget">
          <div className="widget-label">Classification</div>
          <div className="widget-value">
            {latestClassification ? (
              <span className={`badge ${CLASS_BADGE[latestClassification.category] || 'badge-warning'}`}>
                {latestClassification.category}
              </span>
            ) : '—'}
          </div>
        </div>
        <div className="widget">
          <div className="widget-label">Draft Status</div>
          <div className="widget-value pending">
            {latestDraft ? latestDraft.status : '—'}
          </div>
        </div>
      </div>

      <div className="detail-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="card">
          <div className="card-header">
            <h3>Lead Details</h3>
          </div>
          <div className="detail-grid">
            <div className="detail-item">
              <span className="label">ID</span>
              <span className="value">{lead.id}</span>
            </div>
            <div className="detail-item">
              <span className="label">Role</span>
              <span className="value">{lead.role || '—'}</span>
            </div>
            <div className="detail-item">
              <span className="label">Industry</span>
              <span className="value">{lead.industry || '—'}</span>
            </div>
            <div className="detail-item">
              <span className="label">Created</span>
              <span className="value">{new Date(lead.created_at).toLocaleDateString()}</span>
            </div>
            {lead.buying_signals?.length > 0 && (
              <div className="detail-item" style={{ gridColumn: '1 / -1' }}>
                <span className="label">Buying Signals</span>
                <span className="value">{lead.buying_signals.join(', ')}</span>
              </div>
            )}
          </div>
        </div>

        {lead.enrichment && (
          <div className="card">
            <div className="card-header">
              <h3>Enrichment</h3>
            </div>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="label">Company Size</span>
                <span className="value">{lead.enrichment.company_size || '—'}</span>
              </div>
              <div className="detail-item">
                <span className="label">Employees</span>
                <span className="value">{lead.enrichment.employee_count || '—'}</span>
              </div>
              <div className="detail-item">
                <span className="label">Location</span>
                <span className="value">{lead.enrichment.company_location || '—'}</span>
              </div>
              <div className="detail-item">
                <span className="label">Industry</span>
                <span className="value">{lead.enrichment.company_industry || '—'}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {latestDraft && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header">
            <h3>Draft Email</h3>
            <span className={`badge ${latestDraft.status === 'draft' ? 'badge-warning' : 'badge-success'}`}>
              {latestDraft.status}
            </span>
          </div>
          <div className="detail-item" style={{ marginBottom: '0.75rem' }}>
            <span className="label">Subject</span>
            <span className="value">{latestDraft.subject}</span>
          </div>
          <div className="detail-item">
            <span className="label">Body</span>
            <p style={{ whiteSpace: 'pre-wrap', marginTop: '0.25rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
              {latestDraft.body}
            </p>
          </div>
          {(latestDraft.status === 'draft' || latestDraft.status === 'reviewed') && (
            <div className="approval-actions" style={{ marginTop: '1rem' }}>
              <button className="btn btn-success" onClick={handleApprove} disabled={approving}>
                {approving ? 'Processing...' : 'Approve'}
              </button>
              <button className="btn btn-danger" onClick={handleReject} disabled={approving}>
                Reject
              </button>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>Audit Logs</h3>
          {logs && <span style={{ color: 'var(--color-text-dim)', fontSize: '0.875rem' }}>{logs.total} entries</span>}
        </div>
        {logs && logs.entries.length > 0 ? (
          <div className="timeline">
            {logs.entries.map((log) => (
              <div className="timeline-item" key={log.id}>
                <div className="event-type">{log.event_type}</div>
                <div className="message">{log.message}</div>
                <div className="timestamp">{new Date(log.timestamp).toLocaleString()}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="icon">&#128196;</div>
            <h3>No audit logs yet</h3>
            <p>Logs will appear as the pipeline processes this lead.</p>
          </div>
        )}
      </div>
    </div>
  );
}