import { useState, useEffect } from 'react';
import { Upload, Play, ChevronDown } from 'lucide-react';
import { getCustomers } from '../utils/api';

export default function DocumentUpload({ onRun, isRunning }) {
  const [file, setFile] = useState(null);
  const [customerId, setCustomerId] = useState('CUSTOMER_001');
  const [customers, setCustomers] = useState([]);
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    getCustomers()
      .then(setCustomers)
      .catch(() => setCustomers([{ id: 'CUSTOMER_001', name: 'Acme Global Trading Ltd.' }]));
  }, []);

  const handleFile = (f) => {
    const allowed = ['.pdf', '.png', '.jpg', '.jpeg'];
    const ext = f.name.toLowerCase().slice(f.name.lastIndexOf('.'));
    if (allowed.includes(ext)) {
      setFile(f);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = () => {
    if (file && !isRunning) {
      onRun(file, customerId);
    }
  };

  return (
    <div className="bg-gray-900/80 backdrop-blur-sm border border-gray-800 rounded-2xl p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Upload className="w-5 h-5 text-blue-400" />
        Upload Document
      </h2>

      {/* Drop zone */}
      <div
        className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer
          ${dragActive
            ? 'border-blue-400 bg-blue-400/10'
            : file
              ? 'border-emerald-500/50 bg-emerald-500/5'
              : 'border-gray-700 hover:border-gray-500 bg-gray-800/40'
          }`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('file-input').click()}
      >
        <input
          id="file-input"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {file ? (
          <div>
            <p className="text-emerald-400 font-medium">{file.name}</p>
            <p className="text-sm text-gray-400 mt-1">
              {(file.size / 1024).toFixed(1)} KB — Click to change
            </p>
          </div>
        ) : (
          <div>
            <Upload className="w-10 h-10 text-gray-500 mx-auto mb-3" />
            <p className="text-gray-400">Drop a file here or click to browse</p>
            <p className="text-xs text-gray-600 mt-1">PDF, PNG, JPG supported</p>
          </div>
        )}
      </div>

      {/* Customer selector */}
      <div className="relative">
        <label className="block text-sm text-gray-400 mb-1.5">Customer</label>
        <div className="relative">
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                       text-gray-200 appearance-none focus:outline-none focus:ring-2
                       focus:ring-blue-500/50 focus:border-blue-500"
          >
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.id})
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
        </div>
      </div>

      {/* Run button */}
      <button
        onClick={handleSubmit}
        disabled={!file || isRunning}
        className={`w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl
                    font-semibold text-sm transition-all
          ${!file || isRunning
            ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
            : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30'
          }`}
      >
        <Play className="w-4 h-4" />
        {isRunning ? 'Pipeline Running…' : 'Run Pipeline'}
      </button>
    </div>
  );
}
