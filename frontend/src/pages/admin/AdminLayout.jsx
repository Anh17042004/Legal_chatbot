import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import './Admin.css';

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navItems = [
    { path: '/admin', label: 'Dashboard' },
    { path: '/admin/users', label: 'Quản lý Users' },
    { path: '/admin/audit-logs', label: 'Audit Logs' },
    { path: '/chat', label: '← Quay lại Chat' }
  ];

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <h2>Admin Panel</h2>
          <span className="badge">v1.0</span>
        </div>
        <nav className="admin-nav">
          {navItems.map(item => (
            <Link 
              key={item.path} 
              to={item.path}
              className={`admin-nav-item ${location.pathname === item.path ? 'active' : ''}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="admin-footer">
          <div className="admin-user-info">
            <strong>{user?.full_name || user?.email}</strong>
            <span>{user?.role}</span>
          </div>
          <button className="btn btn-ghost" onClick={logout} style={{width: '100%', marginTop: '10px'}}>
            Đăng xuất
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <header className="admin-header">
          <h1>Hệ thống Quản trị Legal AI</h1>
        </header>
        <div className="admin-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
