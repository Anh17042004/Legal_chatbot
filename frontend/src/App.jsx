import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute, PublicRoute } from './components/RouteGuard';

// Pages
import Login from './pages/auth/Login';
import Register from './pages/auth/Register';
import ChatApp from './pages/chat/ChatApp';
import AdminLayout from './pages/admin/AdminLayout';
import Dashboard from './pages/admin/Dashboard';
import Users from './pages/admin/Users';
import AuditLogs from './pages/admin/AuditLogs';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Route>

          {/* Protected Chat Route (User & Admin both can access if needed, but primarily User) */}
          <Route element={<ProtectedRoute allowedRoles={['user', 'admin']} />}>
            <Route path="/chat" element={<ChatApp />} />
          </Route>

          {/* Protected Admin Routes */}
          <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="users" element={<Users />} />
              <Route path="audit-logs" element={<AuditLogs />} />
            </Route>
          </Route>

          {/* Root Redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
