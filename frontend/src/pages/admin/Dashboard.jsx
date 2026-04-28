import React, { useState, useEffect } from 'react';
import { adminApi } from '../../api/adminApi';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSummary();
  }, []);

  const loadSummary = async () => {
    try {
      const data = await adminApi.getSummary();
      setSummary(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Đang tải dữ liệu...</div>;
  if (!summary) return <div>Lỗi tải dữ liệu</div>;

  return (
    <div className="dashboard-container">
      <h2>Tổng quan</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-title">Tổng Users</div>
          <div className="stat-value">{summary.total_users}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Users Active</div>
          <div className="stat-value">{summary.active_users}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Tổng Sessions</div>
          <div className="stat-value">{summary.total_sessions}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title">Tổng Logs</div>
          <div className="stat-value">{summary.total_audit_logs}</div>
        </div>
      </div>

      <div className="recent-logs-section mt-4">
        <h3>Logs tương tác gần đây</h3>
        <div className="table-responsive">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Session ID</th>
                <th>Câu hỏi (User)</th>
                <th>Time (s)</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_logs.map(log => (
                <tr key={log.id}>
                  <td>{new Date(log.created_at).toLocaleString('vi-VN')}</td>
                  <td className="mono">{log.session_id.substring(0, 10)}...</td>
                  <td className="truncate-text">{log.user_query}</td>
                  <td>{log.processing_time?.toFixed(2)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
