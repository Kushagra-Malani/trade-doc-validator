import { Route } from 'lucide-react';
import AmendmentDraft from './AmendmentDraft';

const DECISION_CONFIG = {
  auto_approve: {
    banner: 'bg-gradient-to-r from-emerald-600/30 to-emerald-500/10 border-emerald-500/30',
    text: 'text-emerald-400',
    label: '✅ AUTO-APPROVED',
  },
  flag_for_review: {
    banner: 'bg-gradient-to-r from-yellow-600/30 to-yellow-500/10 border-yellow-500/30',
    text: 'text-yellow-400',
    label: '⚠️ FLAGGED FOR REVIEW',
  },
  request_amendment: {
    banner: 'bg-gradient-to-r from-red-600/30 to-red-500/10 border-red-500/30',
    text: 'text-red-400',
    label: '❌ AMENDMENT REQUIRED',
  },
};

export default function DecisionView({ routing }) {
  if (!routing) return null;

  const decision = routing.decision;
  const cfg = DECISION_CONFIG[decision] || DECISION_CONFIG.flag_for_review;

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Route className="w-5 h-5 text-amber-400" />
        Routing Decision
      </h2>

      {/* Decision banner */}
      <div className={`${cfg.banner} border rounded-xl px-6 py-5`}>
        <p className={`text-xl font-bold ${cfg.text}`}>{cfg.label}</p>
      </div>

      {/* Reasoning */}
      <p className="text-sm text-gray-300 leading-relaxed">{routing.reasoning}</p>

      {/* Amendment draft */}
      {decision === 'request_amendment' && routing.amendment_email_draft && (
        <div className="pt-2 space-y-2">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Draft Amendment Email
          </h3>
          <AmendmentDraft
            draft={routing.amendment_email_draft}
            discrepancies={routing.discrepancies || []}
          />
        </div>
      )}
    </div>
  );
}
