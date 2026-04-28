import React, { useState, useEffect } from 'react';
import { adminApi } from '../../api/adminApi';

export default function AuditLogs() {
  const [data, setData] = useState({ data: [], total: 0, page: 1, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedRow, setExpandedRow] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);

  const notifyAuditLogsChanged = () => {
    const timestamp = String(Date.now());
    localStorage.setItem('auditLogsUpdatedAt', timestamp);
    window.dispatchEvent(new Event('audit-logs-updated'));
  };

  const detailFieldOrder = [
    'id',
    'user_id',
    'session_id',
    'user_query',
    'rewritten_query',
    'bot_response',
    'references',
    'processing_time',
    'created_at',
  ];

  const detailFieldLabels = {
    id: 'ID',
    user_id: 'User ID',
    session_id: 'Session ID',
    user_query: 'Câu hỏi (Gốc)',
    rewritten_query: 'Câu hỏi Rewritten (Search Vector)',
    bot_response: 'Câu trả lời của Bot',
    references: 'Nguồn tham chiếu (References JSON)',
    processing_time: 'Thời gian xử lý (s)',
    created_at: 'Thời gian tạo',
  };

  useEffect(() => {
    loadLogs(1);
  }, []);

  const loadLogs = async (pageToLoad) => {
    setLoading(true);
    try {
      const res = await adminApi.getAuditLogs(pageToLoad, 20, search);
      setData(res);
      setSelectedIds([]); // Clear selection on page change
    } catch (err) {
      console.error(err);
      alert('Lỗi tải Audit Logs');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    loadLogs(1);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bạn có chắc muốn xóa log này?')) return;
    try {
      await adminApi.deleteAuditLog(id);
      notifyAuditLogsChanged();
      loadLogs(data.page);
    } catch (err) {
      alert('Lỗi xóa log');
    }
  };

  const toggleExpand = (id) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedIds(data.data.map(log => log.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleSelectOne = (id) => {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter(selectedId => selectedId !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  };

  const handleBulkDelete = async () => {
    if (!window.confirm(`Bạn có chắc muốn xóa ${selectedIds.length} mục đã chọn?`)) return;
    try {
      await Promise.all(selectedIds.map(id => adminApi.deleteAuditLog(id)));
      notifyAuditLogsChanged();
      setSelectedIds([]);
      loadLogs(data.page);
    } catch (err) {
      alert('Có lỗi xảy ra khi xóa hàng loạt');
    }
  };

  const getDetailFields = (log) => {
    const ordered = detailFieldOrder
      .filter((field) => Object.prototype.hasOwnProperty.call(log, field))
      .map((field) => [field, log[field]]);

    const remaining = Object.entries(log).filter(
      ([field]) => !detailFieldOrder.includes(field)
    );

    return [...ordered, ...remaining];
  };

  const renderDetailValue = (field, value) => {
    if (value === null || value === undefined || value === '') {
      return <div className="code-box">-</div>;
    }

    if (field === 'created_at') {
      return <div className="code-box">{new Date(value).toLocaleString('vi-VN')}</div>;
    }

    if (typeof value === 'object') {
      return (
        <pre className="code-box pre-wrap">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    return <div className="code-box">{String(value)}</div>;
  };

  return (
    <div className="audit-logs-container">
      <div className="flex-between align-center mb-4">
        <h2>Lịch sử hệ thống (Audit Logs)</h2>
        <div style={{display: 'flex', gap: '10px', alignItems: 'center'}}>
          {selectedIds.length > 0 && (
            <button 
              className="btn btn-danger" 
              onClick={handleBulkDelete}
            >
              Xóa {selectedIds.length} mục
            </button>
          )}
          <form onSubmit={handleSearch} className="search-form" style={{margin: 0}}>
            <input 
              type="text" 
              className="input" 
              placeholder="Tìm session / câu hỏi..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <button type="submit" className="btn btn-primary">Tìm</button>
          </form>
        </div>
      </div>

      {loading ? (
        <div>Đang tải...</div>
      ) : (
        <div className="table-responsive">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{width: '40px', textAlign: 'center'}}>
                  <input 
                    type="checkbox" 
                    checked={data.data.length > 0 && selectedIds.length === data.data.length}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>ID</th>
                <th>Thời gian</th>
                <th>Session ID</th>
                <th>User ID</th>
                <th>Câu hỏi (Gốc)</th>
                <th>Time (s)</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map(log => (
                <React.Fragment key={log.id}>
                  <tr className={selectedIds.includes(log.id) ? 'selected-row' : ''}>
                    <td style={{textAlign: 'center'}}>
                      <input 
                        type="checkbox" 
                        checked={selectedIds.includes(log.id)}
                        onChange={() => handleSelectOne(log.id)}
                      />
                    </td>
                    <td>{log.id}</td>
                    <td>{new Date(log.created_at).toLocaleString('vi-VN')}</td>
                    <td className="mono">{log.session_id.substring(0, 10)}...</td>
                    <td>{log.user_id || 'Anon'}</td>
                    <td className="truncate-text" title={log.user_query}>{log.user_query}</td>
                    <td>{log.processing_time?.toFixed(2)}</td>
                    <td>
                      <button className="btn btn-ghost btn-sm mr-2" onClick={() => toggleExpand(log.id)}>
                        {expandedRow === log.id ? 'Đóng' : 'Chi tiết'}
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(log.id)}>
                        Xóa
                      </button>
                    </td>
                  </tr>
                  {expandedRow === log.id && (
                    <tr className="expanded-row">
                      <td colSpan="8">
                        <div className="expanded-content">
                          {getDetailFields(log).map(([field, value], index) => (
                            <div
                              key={field}
                              className={`log-detail-section ${index > 0 ? 'mt-3' : ''}`}
                            >
                              <strong>{detailFieldLabels[field] || field}:</strong>
                              {renderDetailValue(field, value)}
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          
          <div className="pagination">
            <button 
              className="btn btn-ghost" 
              disabled={data.page <= 1}
              onClick={() => loadLogs(data.page - 1)}
            >
              Trước
            </button>
            <span style={{margin: '0 10px'}}>Trang {data.page} / {data.total_pages}</span>
            <button 
              className="btn btn-ghost" 
              disabled={data.page >= data.total_pages}
              onClick={() => loadLogs(data.page + 1)}
            >
              Sau
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
