import { useState, useEffect } from 'react';
import { getDashboardStats } from '../api';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDashboardStats()
      .then(setStats)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return <div className="alert alert-error">Failed to load dashboard: {error}</div>;
  }

  const widgets = [
    { label: 'Total Leads', value: stats.total_leads, color: 'primary' },
    { label: 'Hot Leads', value: stats.hot_leads, color: 'hot' },
    { label: 'Nurture Leads', value: stats.nurture_leads, color: 'nurture' },
    { label: 'Disqualified', value: stats.disqualify_leads, color: 'disqualify' },
    { label: 'Pending Approval', value: stats.pending_approvals, color: 'pending' },
    { label: 'Emails Sent', value: stats.emails_sent, color: 'success' },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Pipeline overview and key metrics</p>
      </div>

      <div className="widget-grid">
        {widgets.map((w) => (
          <div className="widget" key={w.label}>
            <div className="widget-label">{w.label}</div>
            <div className={`widget-value ${w.color}`}>{w.value}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Pipeline Summary</h2>
        </div>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="label">Leads with Scores</span>
            <span className="value">{stats.leads_with_scores}</span>
          </div>
          <div className="detail-item">
            <span className="label">Leads Classified</span>
            <span className="value">{stats.leads_classified}</span>
          </div>
          <div className="detail-item">
            <span className="label">Leads with Drafts</span>
            <span className="value">{stats.leads_with_drafts}</span>
          </div>
          <div className="detail-item">
            <span className="label">Approved</span>
            <span className="value">{stats.approved}</span>
          </div>
          <div className="detail-item">
            <span className="label">Rejected</span>
            <span className="value">{stats.rejected}</span>
          </div>
          <div className="detail-item">
            <span className="label">Average Score</span>
            <span className="value">{stats.avg_score}</span>
          </div>
        </div>
      </div>
    </div>
  );
}