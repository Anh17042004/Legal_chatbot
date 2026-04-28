import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export const ProtectedRoute = ({ allowedRoles }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return <div style={{color:'white', padding: 20}}>Đang tải...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <div style={{
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'center', 
        justifyContent: 'center', 
        height: '100vh', 
        color: 'var(--text-primary)',
        backgroundColor: 'var(--bg-base)'
      }}>
        <h1 style={{color: '#f87171', fontSize: '2rem', marginBottom: '10px'}}>403 - Truy cập bị từ chối</h1>
        <p>Tài khoản của bạn không có quyền quản trị để vào trang này.</p>
        <button 
          onClick={() => window.location.href = '/chat'}
          style={{
            marginTop: '20px',
            padding: '10px 20px',
            backgroundColor: 'var(--accent)',
            color: 'white',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer',
            fontSize: '1rem'
          }}
        >
          Quay lại trang Chat
        </button>
      </div>
    );
  }

  return <Outlet />;
};

export const PublicRoute = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return null;
  }

  if (user) {
    return <Navigate to="/chat" replace />;
  }

  return <Outlet />;
};
