import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function AmendmentDraft({ draft, discrepancies = [] }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = draft;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-4">
      {/* Discrepancy summary */}
      {discrepancies.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-700">
                <th className="pb-2 font-medium">Field</th>
                <th className="pb-2 font-medium">Found</th>
                <th className="pb-2 font-medium">Expected</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {discrepancies.map((d, i) => (
                <tr key={i} className="bg-red-500/5">
                  <td className="py-2 text-gray-300 font-mono">{d.field}</td>
                  <td className="py-2 text-red-300">{d.found}</td>
                  <td className="py-2 text-emerald-300">{d.expected}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Draft email */}
      <div className="relative">
        <pre className="bg-gray-950 border border-gray-700 rounded-lg p-4 text-sm text-gray-300
                        whitespace-pre-wrap font-sans leading-relaxed max-h-[300px] overflow-y-auto">
          {draft}
        </pre>
        <button
          onClick={handleCopy}
          className={`absolute top-3 right-3 flex items-center gap-1.5 text-xs px-3 py-1.5
                      rounded-lg transition-all font-medium
            ${copied
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-gray-800 text-gray-400 border border-gray-700 hover:text-white hover:bg-gray-700'
            }`}
        >
          {copied ? <><Check className="w-3.5 h-3.5" /> Copied!</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
        </button>
      </div>
    </div>
  );
}
