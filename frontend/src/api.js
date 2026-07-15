/**
 * PipelineIQ API Service Layer
 *
 * Centralised API client for all backend endpoints.
 * Base URL is proxied through Vite in dev, or direct in production.
 */

const API_BASE = '/api';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    // FastAPI validation errors (422) return body.detail as an array of objects.
    // Normalise it to a plain string so callers can safely use err.message.
    let detail = body.detail;
    if (Array.isArray(detail)) {
      detail = detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
    } else if (detail && typeof detail === 'object') {
      detail = JSON.stringify(detail);
    }
    const err = new Error(detail || `HTTP ${response.status}`);
    err.status = response.status;
    err.body = body;
    throw err;
  }

  if (response.status === 204) return null;
  return response.json();
}

// ── Pipeline ─────────────────────────────────────────────────────────────

export async function runPipeline(leadData) {
  return request('/pipeline/run', {
    method: 'POST',
    body: JSON.stringify({ lead: leadData }),
  });
}

// ── Leads ────────────────────────────────────────────────────────────────

export async function createLead(data) {
  return request('/lead', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getLead(leadId) {
  return request(`/lead/${leadId}`);
}

export async function listLeads(params = {}) {
  const qs = new URLSearchParams();
  if (params.search) qs.set('search', params.search);
  if (params.industry) qs.set('industry', params.industry);
  if (params.sort_by) qs.set('sort_by', params.sort_by);
  if (params.sort_order) qs.set('sort_order', params.sort_order);
  if (params.limit) qs.set('limit', params.limit);
  if (params.offset) qs.set('offset', params.offset);
  const query = qs.toString();
  return request(`/leads${query ? `?${query}` : ''}`);
}

// ── Approvals ────────────────────────────────────────────────────────────

export async function approveDraft(leadId, data) {
  return request(`/approve/${leadId}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function rejectDraft(leadId, data) {
  return request(`/reject/${leadId}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function editDraft(leadId, data) {
  return request(`/draft/${leadId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function listPendingApprovals() {
  return request('/pending-approvals');
}

// ── Audit Logs ───────────────────────────────────────────────────────────

export async function getAuditLogs(leadId, params = {}) {
  const qs = new URLSearchParams();
  if (params.event_type) qs.set('event_type', params.event_type);
  if (params.sort_by) qs.set('sort_by', params.sort_by);
  if (params.sort_order) qs.set('sort_order', params.sort_order);
  if (params.limit) qs.set('limit', params.limit);
  if (params.offset) qs.set('offset', params.offset);
  const query = qs.toString();
  return request(`/logs/${leadId}${query ? `?${query}` : ''}`);
}

// ── Dashboard ────────────────────────────────────────────────────────────

export async function getDashboardStats() {
  return request('/dashboard-stats');
}

// ── Health ───────────────────────────────────────────────────────────────

export async function healthCheck() {
  return request('/health');
}