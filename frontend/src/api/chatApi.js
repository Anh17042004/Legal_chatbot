import { apiFetch } from './client';

export const chatApi = {
  getSessions: () => apiFetch('/chat/sessions'),
  
  getHistory: (sessionId) => apiFetch(`/chat/history/${sessionId}`),
};
