import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import AddLead from './pages/AddLead';
import LeadDetail from './pages/LeadDetail';
import LeadsList from './pages/LeadsList';
import PendingApprovals from './pages/PendingApprovals';
import AuditLogs from './pages/AuditLogs';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/add-lead" element={<AddLead />} />
            <Route path="/lead/:id" element={<LeadDetail />} />
            <Route path="/leads" element={<LeadsList />} />
            <Route path="/pending-approvals" element={<PendingApprovals />} />
            <Route path="/audit-logs" element={<AuditLogs />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function Sidebar() {
  const navItems = [
    { path: '/', label: 'Dashboard', icon: '\u2302' },
    { path: '/leads', label: 'Leads', icon: '\u2630' },
    { path: '/add-lead', label: 'Add Lead', icon: '+' },
    { path: '/pending-approvals', label: 'Pending Approvals', icon: '\u2691' },
    { path: '/audit-logs', label: 'Audit Logs', icon: '\u2637' },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <h1>PipelineIQ</h1>
        <p>Lead Qualification & Outreach</p>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}