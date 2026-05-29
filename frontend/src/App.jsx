import { usePipeline } from './hooks/usePipeline';
import DocumentUpload from './components/DocumentUpload';
import PipelineStatus from './components/PipelineStatus';
import ExtractionView from './components/ExtractionView';
import ValidationView from './components/ValidationView';
import DecisionView from './components/DecisionView';
import QueryInterface from './components/QueryInterface';

export default function App() {
  const { status, result, error, runPipeline, reset } = usePipeline();
  const isRunning = status === 'uploading' || status === 'running';
  const hasResults = status === 'complete' && result;

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent">
              Trade Document Validator
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">Nova POC · GoComet</p>
          </div>
          {hasResults && (
            <button
              onClick={reset}
              className="text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700
                         px-4 py-2 rounded-lg transition-all border border-gray-700"
            >
              New Document
            </button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Top section: Upload + Status */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Upload */}
          <DocumentUpload onRun={runPipeline} isRunning={isRunning} />

          {/* Right: Pipeline Status */}
          <PipelineStatus status={status} result={result} error={error} />
        </div>

        {/* Results section — only visible after pipeline completes */}
        {hasResults && (
          <div className="space-y-6">
            <ExtractionView extraction={result.extraction} />
            <ValidationView validation={result.validation} />
            <DecisionView routing={result.routing} />
          </div>
        )}

        {/* Query interface — always visible */}
        <QueryInterface hasResults={!!hasResults} />
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-12">
        <div className="max-w-7xl mx-auto px-6 py-4 text-center text-xs text-gray-600">
          Trade Document Validator — Multi-Agent Pipeline POC · Built for GoComet Nova
        </div>
      </footer>
    </div>
  );
}
