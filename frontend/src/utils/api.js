import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 min — pipeline can take a while
});

/**
 * Upload a file and run the validation pipeline.
 * @param {File} file
 * @param {string} customerId
 * @returns {Promise<object>} Pipeline result
 */
export async function runPipeline(file, customerId) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('customer_id', customerId);
  const { data } = await api.post('/pipeline/run', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/**
 * Poll pipeline status by run_id.
 * @param {string} runId
 * @returns {Promise<object>}
 */
export async function getStatus(runId) {
  const { data } = await api.get(`/pipeline/status/${runId}`);
  return data;
}

/**
 * Send a natural-language query.
 * @param {string} question
 * @returns {Promise<object>} QueryResponse
 */
export async function queryData(question) {
  const { data } = await api.post('/query', { question });
  return data;
}

/**
 * Fetch available customers.
 * @returns {Promise<Array>} [{id, name}]
 */
export async function getCustomers() {
  const { data } = await api.get('/customers');
  return data;
}

export default api;
