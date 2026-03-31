import axios from 'axios';

const api = axios.create({
  baseURL: '/api/dashboard',
  timeout: 10000,
});

// Add auth token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const getSummary = () => api.get('/summary');
export const getErrors = (params) => api.get('/errors', { params });
export const getErrorById = (id) => api.get(`/errors/${id}`);
export const getTimeline = (days = 7) => api.get('/stats/timeline', { params: { days } });
export const getErrorsByType = (days = 7) => api.get('/stats/by-type', { params: { days } });
export const getHistory = (params) => api.get('/history', { params });
export const getServices = () => api.get('/services');
export const addService = (data) => api.post('/services', data);
export const updateService = (id, data) => api.put(`/services/${id}`, data);
export const deleteService = (id) => api.delete(`/services/${id}`);

// Service detail + members (uses /api/services base)
const svcApi = axios.create({ baseURL: '/api/services', timeout: 10000 });
svcApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const getServiceDetail = (id) => svcApi.get(`/${id}`);
export const getServiceMembers = (id) => svcApi.get(`/${id}/members`);
export const inviteMember = (id, email) => svcApi.post(`/${id}/members`, { email });
export const removeMember = (serviceId, userId) => svcApi.delete(`/${serviceId}/members/${userId}`);

export default api;
