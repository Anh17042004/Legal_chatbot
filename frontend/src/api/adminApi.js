import { apiFetch } from './client';

export const adminApi = {
  getSummary: () => apiFetch('/admin/summary'),
  
  getAuditLogs: (page = 1, size = 20, search = '') => {
    const params = new URLSearchParams({ page, size });
    if (search) params.append('search', search);
    return apiFetch(`/admin/audit-logs?${params.toString()}`);
  },
  
  deleteAuditLog: (id) => apiFetch(`/admin/audit-logs/${id}`, { method: 'DELETE' }),
  
  getUsers: (page = 1, size = 20, search = '') => {
    const params = new URLSearchParams({ page, size });
    if (search) params.append('search', search);
    return apiFetch(`/users?${params.toString()}`);
  },
  
  updateUser: (id, data) => apiFetch(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  
  deleteUser: (id) => apiFetch(`/users/${id}`, { method: 'DELETE' })
};
