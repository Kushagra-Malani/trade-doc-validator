import { useState, useCallback, useRef } from 'react';
import { runPipeline as apiRunPipeline, getStatus } from '../utils/api';

/**
 * Custom hook that manages the full pipeline lifecycle.
 *
 * States:
 *   status  — 'idle' | 'uploading' | 'running' | 'complete' | 'error'
 *   result  — full pipeline result object (null until complete)
 *   error   — error message string (null unless status is 'error')
 *
 * Actions:
 *   runPipeline(file, customerId)  — upload + run + poll
 *   reset()                        — clear all state back to idle
 */
export function usePipeline() {
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const reset = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    setStatus('idle');
    setResult(null);
    setError(null);
  }, []);

  const runPipeline = useCallback(async (file, customerId) => {
    reset();
    setStatus('uploading');

    try {
      // POST the file — backend runs pipeline synchronously and returns result
      const data = await apiRunPipeline(file, customerId);

      // If the backend returned the full result immediately (sync POC mode)
      if (data.status === 'complete' || data.status === 'error') {
        setResult(data);
        setStatus(data.status);
        if (data.status === 'error') {
          setError(data.errors?.join('; ') || 'Pipeline failed');
        }
        return;
      }

      // Otherwise poll for status
      setStatus('running');
      const runId = data.run_id;

      pollRef.current = setInterval(async () => {
        try {
          const statusData = await getStatus(runId);
          setResult(statusData);

          if (statusData.status === 'complete' || statusData.status === 'error') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setStatus(statusData.status);
            if (statusData.status === 'error') {
              setError(statusData.errors?.join('; ') || 'Pipeline failed');
            }
          }
        } catch (pollErr) {
          // Silently retry on poll failure — backend might still be running
          console.warn('Poll error:', pollErr);
        }
      }, 1500);
    } catch (err) {
      setStatus('error');
      setError(err.response?.data?.detail || err.message || 'Upload failed');
    }
  }, [reset]);

  return { status, result, error, runPipeline, reset };
}
