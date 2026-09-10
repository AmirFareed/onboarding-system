import api from './api';

export function startProcessing(applicationId) {
  return api.post(`/applications/${applicationId}/processing/start`).then((response) => response.data);
}

export function getProcessingProgress(applicationId) {
  return api.get(`/applications/${applicationId}/processing/progress`).then((response) => response.data);
}

export function getProcessingDocuments(applicationId) {
  return api.get(`/applications/${applicationId}/processing/documents`).then((response) => response.data);
}

export function retryProcessing(applicationId) {
  return api.post(`/applications/${applicationId}/processing/retry`).then((response) => response.data);
}
