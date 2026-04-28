import React, { useState, useEffect } from 'react';
import { adminApi } from '../../api/adminApi';

export default function Users() {
  const [data, setData] = useState({ data: [], total: 0, page: 1, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);

  useEffect(() => {
    loadUsers(1);
  }, []);

  const loadUsers = async (pageToLoad) => {
    setLoading(true);
    try {
      const res = await adminApi.getUsers(pageToLoad, 20, search);
      setData(res);
      setSelectedIds([]); // Xóa selection cũ khi đổi trang
    } catch (err) {
      console.error(err);
      alert('Lỗi khi tải danh sách User');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    loadUsers(1);
  };

  const toggleActive = async (user) => {
    try {
      await adminApi.updateUser(user.id, { is_active: !user.is_active });
      loadUsers(data.page);
    } catch (err) {
      alert('Lỗi cập nhật trạng thái');
    }
  };

  const changeRole = async (user, newRole) => {
    try {
      await adminApi.updateUser(user.id, { role: newRole });
      loadUsers(data.page);
    } catch (err) {
      alert('Lỗi cập nhật role');
    }
  };

  const handleEditCredits = async (user) => {
    const newCreditsStr = window.prompt(`Nhập số Credit mới cho user ${user.email}:`, user.credits);
    if (newCreditsStr === null) return; 
    const newCredits = parseInt(newCreditsStr, 10);
    if (isNaN(newCredits) || newCredits < 0) {
      alert('Vui lòng nhập một số nguyên hợp lệ (>= 0)');
      return;
    }
    try {
      await adminApi.updateUser(user.id, { credits: newCredits });
      loadUsers(data.page);
    } catch (err) {
      alert('Lỗi cập nhật Credit');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bạn có chắc muốn xóa user này? Mọi dữ liệu liên quan sẽ bị xóa.')) return;
    try {
      await adminApi.deleteUser(id);
      loadUsers(data.page);
    } catch (err) {
      alert('Lỗi xóa user');
    }
  };

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedIds(data.data.map(user => user.id));
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
    if (!window.confirm(`CẢNH BÁO: Bạn có chắc muốn xóa vĩnh viễn ${selectedIds.length} users đã chọn cùng toàn bộ dữ liệu của họ?`)) return;
    try {
      await Promise.all(selectedIds.map(id => adminApi.deleteUser(id)));
      setSelectedIds([]);
      loadUsers(data.page);
    } catch (err) {
      alert('Có lỗi xảy ra khi xóa hàng loạt');
    }
  };

  return (
    <div className="users-container">
      <div className="flex-between align-center mb-4">
        <h2>Quản lý Users</h2>
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
              placeholder="Tìm theo email / tên..." 
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
                <th>Email</th>
                <th>Tên</th>
                <th>Credits</th>
                <th>Trạng thái</th>
                <th>Quyền</th>
                <th>Ngày tạo</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map(user => (
                <tr key={user.id} className={selectedIds.includes(user.id) ? 'selected-row' : ''}>
                  <td style={{textAlign: 'center'}}>
                    <input 
                      type="checkbox" 
                      checked={selectedIds.includes(user.id)}
                      onChange={() => handleSelectOne(user.id)}
                    />
                  </td>
                  <td>{user.id}</td>
                  <td>{user.email}</td>
                  <td>{user.full_name || '-'}</td>
                  <td 
                    onClick={() => handleEditCredits(user)}
                    style={{cursor: 'pointer', color: 'var(--primary-color)', fontWeight: 'bold'}}
                    title="Nhấn để sửa Credit"
                  >
                    {user.credits} ✏️
                  </td>
                  <td>
                    <label style={{display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer'}}>
                      <input 
                        type="checkbox" 
                        checked={user.is_active}
                        onChange={() => toggleActive(user)}
                      />
                      <span style={{fontSize: '13px', fontWeight: '500', color: user.is_active ? 'var(--text-primary)' : 'var(--danger-color)'}}>
                        {user.is_active ? 'Active' : 'Locked'}
                      </span>
                    </label>
                  </td>
                  <td>
                    <select 
                      value={user.role} 
                      onChange={(e) => changeRole(user, e.target.value)}
                      className="role-select"
                    >
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td>{new Date(user.created_at).toLocaleDateString('vi-VN')}</td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(user.id)}>
                      Xóa
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          
          <div className="pagination">
            <button 
              className="btn btn-ghost" 
              disabled={data.page <= 1}
              onClick={() => loadUsers(data.page - 1)}
            >
              Trước
            </button>
            <span style={{margin: '0 10px'}}>Trang {data.page} / {data.total_pages}</span>
            <button 
              className="btn btn-ghost" 
              disabled={data.page >= data.total_pages}
              onClick={() => loadUsers(data.page + 1)}
            >
              Sau
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
