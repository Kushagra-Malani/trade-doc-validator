import { useState } from 'react';
import { Search, ChevronDown, ChevronUp, Loader2, Database } from 'lucide-react';
import { queryData } from '../utils/api';

const SUGGESTIONS = [
  'How many shipments have been processed?',
  'How many were flagged for review?',
  'Show all mismatched fields',
  'What is the total cost today?',
];

export default function QueryInterface({ hasResults }) {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [showSql, setShowSql] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (q) => {
    const query = q || question;
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const data = await queryData(query);
      setResponse(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Query failed');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Database className="w-5 h-5 text-teal-400" />
        Query Verified Data
      </h2>

      {!hasResults && (
        <p className="text-sm text-gray-500 italic">
          Process a document first to query results.
        </p>
      )}

      {/* Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your verified data…"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                     text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2
                     focus:ring-teal-500/50 focus:border-teal-500 text-sm"
        />
        <button
          onClick={() => handleSubmit()}
          disabled={loading || !question.trim()}
          className={`px-4 py-2.5 rounded-lg flex items-center gap-2 text-sm font-medium transition-all
            ${loading || !question.trim()
              ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
              : 'bg-teal-600 hover:bg-teal-500 text-white'
            }`}
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        </button>
      </div>

      {/* Suggestion chips */}
      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => { setQuestion(s); handleSubmit(s); }}
            className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white
                       px-3 py-1.5 rounded-full border border-gray-700 transition-all"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Response */}
      {response && (
        <div className="space-y-3">
          {/* Answer */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-xl px-5 py-4">
            <p className="text-sm text-gray-200 leading-relaxed font-medium">{response.answer}</p>
          </div>

          {/* SQL toggle */}
          <button
            onClick={() => setShowSql(!showSql)}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showSql ? 'Hide SQL' : 'Show SQL'}
          </button>

          {showSql && (
            <pre className="bg-gray-950 border border-gray-700 rounded-lg px-4 py-3
                            text-xs text-teal-300 font-mono overflow-x-auto">
              {response.sql_generated}
            </pre>
          )}

          {/* Raw rows */}
          {response.rows?.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-400 border-b border-gray-700">
                    {Object.keys(response.rows[0]).map((k) => (
                      <th key={k} className="pb-2 font-medium px-2">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {response.rows.slice(0, 20).map((row, i) => (
                    <tr key={i} className="hover:bg-gray-800/30">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="py-2 px-2 text-gray-300">{String(v ?? '—')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
