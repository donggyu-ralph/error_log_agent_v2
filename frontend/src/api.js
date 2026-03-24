import axios from 'axios';

const api = axios.create({
  baseURL: '/api/dashboard',
  timeout: 10000,
});

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

export default api;
