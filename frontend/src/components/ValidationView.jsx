import { ShieldCheck } from 'lucide-react';

const STATUS_CONFIG = {
  match:          { icon: '✅', label: 'Match',      bg: 'bg-emerald-500/8',  border: 'border-emerald-500/20', text: 'text-emerald-400' },
  mismatch:       { icon: '❌', label: 'Mismatch',   bg: 'bg-red-500/8',      border: 'border-red-500/20',     text: 'text-red-400' },
  uncertain:      { icon: '⚠️',  label: 'Uncertain',  bg: 'bg-yellow-500/8',   border: 'border-yellow-500/20',  text: 'text-yellow-400' },
  not_applicable: { icon: '➖', label: 'N/A',        bg: 'bg-gray-500/8',     border: 'border-gray-500/20',    text: 'text-gray-400' },
};

export default function ValidationView({ validation }) {
  if (!validation) return null;

  const fieldResults = validation.field_results || [];
  const score = validation.overall_score ?? validation.overall_validation_score ?? 0;
  const scoreColor = score >= 0.8 ? 'text-emerald-400' : score >= 0.5 ? 'text-yellow-400' : 'text-red-400';
  const scoreBg = score >= 0.8 ? 'from-emerald-500/20 to-emerald-500/5' : score >= 0.5 ? 'from-yellow-500/20 to-yellow-500/5' : 'from-red-500/20 to-red-500/5';

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-cyan-400" />
          Validation Results
        </h2>
      </div>

      {/* Score banner */}
      <div className={`bg-gradient-to-r ${scoreBg} rounded-xl px-5 py-4 flex items-center justify-between`}>
        <span className="text-sm text-gray-300">Overall Validation Score</span>
        <span className={`text-3xl font-bold ${scoreColor}`}>
          {Math.round(score * 100)}%
        </span>
      </div>

      {/* Results table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-800">
              <th className="pb-3 font-medium">Field</th>
              <th className="pb-3 font-medium">Status</th>
              <th className="pb-3 font-medium">Found</th>
              <th className="pb-3 font-medium">Expected</th>
              <th className="pb-3 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {fieldResults.map((r) => {
              const cfg = STATUS_CONFIG[r.status] || STATUS_CONFIG.not_applicable;
              return (
                <tr key={r.field_name} className={`${cfg.bg} transition-colors`}>
                  <td className="py-3 text-gray-300 font-mono text-xs">{r.field_name}</td>
                  <td className="py-3">
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${cfg.text}`}>
                      {cfg.icon} {cfg.label}
                    </span>
                  </td>
                  <td className="py-3 text-white text-xs">{r.extracted_value || '—'}</td>
                  <td className="py-3 text-gray-400 text-xs">{r.expected_value || '—'}</td>
                  <td className="py-3 text-gray-500 text-xs max-w-[200px] truncate" title={r.reason}>
                    {r.reason || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
