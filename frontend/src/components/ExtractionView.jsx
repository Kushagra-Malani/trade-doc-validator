import { FileSearch, Eye } from 'lucide-react';

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.8 ? 'bg-emerald-500' :
    value >= 0.6 ? 'bg-yellow-500' :
    'bg-red-500';

  const textColor =
    value >= 0.8 ? 'text-emerald-400' :
    value >= 0.6 ? 'text-yellow-400' :
    'text-red-400';

  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-mono font-semibold ${textColor} w-10 text-right`}>{pct}%</span>
    </div>
  );
}

export default function ExtractionView({ extraction }) {
  if (!extraction) return null;

  const fields = extraction.fields || [];
  const docType = extraction.document_type || 'unknown';
  const model = extraction.extraction_model || extraction.model || '—';

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <FileSearch className="w-5 h-5 text-violet-400" />
          Extraction Results
        </h2>
        <div className="flex gap-3 text-xs text-gray-500">
          <span className="bg-gray-800 px-2 py-1 rounded-md">
            {docType.replace(/_/g, ' ')}
          </span>
          <span className="bg-gray-800 px-2 py-1 rounded-md">{model}</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-800">
              <th className="pb-3 font-medium">Field</th>
              <th className="pb-3 font-medium">Extracted Value</th>
              <th className="pb-3 font-medium pl-4">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {fields.map((f) => {
              const name = f.field_name;
              const value = f.value ?? f.extracted_value;
              const conf = f.confidence ?? 0;
              return (
                <tr key={name} className="hover:bg-gray-800/30 transition-colors">
                  <td className="py-3 text-gray-300 font-mono text-xs">{name}</td>
                  <td className="py-3 text-white">
                    {value || <span className="text-gray-600">—</span>}
                  </td>
                  <td className="py-3 pl-4">
                    <ConfidenceBar value={conf} />
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
