import api from '../services/api';

export function login(credentials) {
  return api
    .post('/auth/login', credentials, { _skipAuthRefresh: true })
    .then((response) => response.data);
}

export function getCurrentUser() {
  return api.get('/auth/me').then((response) => response.data);
}

export function refreshSession() {
  return api.post('/auth/refresh', {}, { _skipAuthRefresh: true });
}

export function logout() {
  return api.post('/auth/logout', {}, { _skipAuthRefresh: true });
}
