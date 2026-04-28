import { apiFetch } from './client';

export const authApi = {
  login: (email, password) =>
    apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (email, password, full_name) =>
    apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name }),
    }),

  me: () => apiFetch('/auth/me'),
};
