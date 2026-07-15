import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { listLeads, getAuditLogs } from '../api';

export default function AuditLogs() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [selectedLead, setSelectedLead] = useState(null);
  const [logs, setLogs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [eventFilter, setEventFilter] = useState('');

  // Load leads list on mount
  useEffect(() => {
    listLeads({ limit: 200 })
      .then((data) => setLeads(data.leads))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load logs when a lead is selected
  useEffect(() => {
    if (!selectedLead) {
      setLogs(null);
      return;
    }
    setLoading(true);
    getAuditLogs(selectedLead, { event_type: eventFilter || undefined, limit: 100 })
      .then(setLogs)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [selectedLead, eventFilter]);

  const totalEvents = logs?.total ?? 0;
  const filteredCount = logs?.filtered_count ?? 0;

  return (
    <div>
      <div className="page-header">
        <h1>Audit Logs</h1>
        <p>Event history for all leads in the pipeline</p>
      </div>

      <div className="search-bar">
        <select
          value={selectedLead || ''}
          onChange={(e) => {
            setSelectedLead(e.target.value || null);
            setError(null);
          }}
          style={{ minWidth: 250 }}
        >
          <option value="">— Select a lead —</option>
          {leads.map((lead) => (
            <option key={lead.id} value={lead.id}>
              {lead.name} - {lead.email}
            </option>
          ))}
        </select>
        <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)}>
          <option value="">All event types</option>
          <option value="lead_created">Lead Created</option>
          <option value="enrichment">Enrichment</option>
          <option value="scoring">Scoring</option>
          <option value="classification">Classification</option>
          <option value="draft_created">Draft Created</option>
          <option value="approval">Approval</option>
          <option value="rejection">Rejection</option>
          <option value="email_sent">Email Sent</option>
          <option value="fairness_check">Fairness Check</option>
          <option value="prompt_injection_detected">Prompt Injection</option>
        </select>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!selectedLead && (
        <div className="empty-state">
          <div className="icon">&#128196;</div>
          <h3>Select a lead</h3>
          <p>Choose a lead from the dropdown to view its audit logs.</p>
        </div>
      )}

      {loading && (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      )}

      {selectedLead && logs && logs.entries.length === 0 && !loading && (
        <div className="empty-state">
          <div className="icon">&#128196;</div>
          <h3>No logs found</h3>
          <p>This lead has no matching audit log entries.</p>
        </div>
      )}

      {selectedLead && logs && logs.entries.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2>
              Logs for{' '}
              <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/lead/${selectedLead}`); }}>
                {leads.find((l) => l.id === selectedLead)?.name || selectedLead}
              </a>
            </h2>
            <span style={{ color: 'var(--color-text-dim)', fontSize: '0.875rem' }}>
              {filteredCount} of {totalEvents} events
            </span>
          </div>
          <div className="timeline">
            {logs.entries.map((log) => (
              <div className="timeline-item" key={log.id}>
                <div className="event-type">{log.event_type}</div>
                <div className="message">{log.message}</div>
                <div className="timestamp">{new Date(log.timestamp).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}