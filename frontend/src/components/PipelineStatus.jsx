import { CheckCircle2, XCircle, Loader2, Circle, DollarSign, Clock } from 'lucide-react';

const STEPS = [
  { key: 'uploading', label: 'Upload' },
  { key: 'extracting', label: 'Extracting' },
  { key: 'validating', label: 'Validating' },
  { key: 'routing', label: 'Routing' },
];

const STATUS_ORDER = { uploading: 0, extracting: 1, validating: 2, routing: 3, complete: 4, error: -1 };

function getStepState(stepIndex, pipelineStatus) {
  if (pipelineStatus === 'idle') return 'pending';
  if (pipelineStatus === 'error') {
    const errIdx = STATUS_ORDER[pipelineStatus] ?? -1;
    // Mark all as done up to the point of failure, then error on current
    return stepIndex <= 3 ? 'error-unknown' : 'pending';
  }
  if (pipelineStatus === 'complete') return 'done';

  const currentIdx = STATUS_ORDER[pipelineStatus] ?? 0;
  if (stepIndex < currentIdx) return 'done';
  if (stepIndex === currentIdx) return 'active';
  return 'pending';
}

export default function PipelineStatus({ status, result, error }) {
  if (status === 'idle') return null;

  const isComplete = status === 'complete';
  const isError = status === 'error';

  // Determine which pipeline phase we're in from the result
  const pipelinePhase = result?.status || status;

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Loader2 className={`w-5 h-5 ${isComplete ? 'text-emerald-400' : isError ? 'text-red-400' : 'text-blue-400 animate-spin'}`} />
        Pipeline Status
      </h2>

      {/* Steps */}
      <div className="space-y-3">
        {STEPS.map((step, i) => {
          const state = isComplete
            ? 'done'
            : isError
              ? (i <= (STATUS_ORDER[pipelinePhase] ?? 0) ? (i === (STATUS_ORDER[pipelinePhase] ?? 0) ? 'error' : 'done') : 'pending')
              : getStepState(i, pipelinePhase);

          return (
            <div key={step.key} className="flex items-center gap-3">
              {state === 'done' && <CheckCircle2 className="w-5 h-5 text-emerald-400" />}
              {state === 'active' && <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />}
              {state === 'error' && <XCircle className="w-5 h-5 text-red-400" />}
              {(state === 'pending' || state === 'error-unknown') && <Circle className="w-5 h-5 text-gray-600" />}
              <span className={`text-sm font-medium ${
                state === 'done' ? 'text-emerald-400' :
                state === 'active' ? 'text-blue-400' :
                state === 'error' ? 'text-red-400' :
                'text-gray-500'
              }`}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Error message */}
      {isError && error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Metrics */}
      {isComplete && result && (
        <div className="flex gap-4 pt-2">
          <div className="flex items-center gap-1.5 text-sm text-gray-400">
            <Clock className="w-4 h-4" />
            <span>{((result.total_latency_ms || 0) / 1000).toFixed(1)}s</span>
          </div>
          <div className="flex items-center gap-1.5 text-sm text-gray-400">
            <DollarSign className="w-4 h-4" />
            <span>${(result.total_cost_usd || 0).toFixed(4)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
