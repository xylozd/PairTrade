import { useState } from 'react';

function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <header className="mb-8 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center">
          <span className="text-white text-sm font-semibold">P</span>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">NSE Intraday Pair Trading</h1>
          <p className="text-gray-600 text-sm">Paper-trading mode · Phase 0 foundation complete</p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-4">
          <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
            <h2 className="text-lg font-semibold mb-4">Status</h2>
            <p className="text-gray-600">
              Backend health endpoint · CORS · Pydantic schemas · Config with
              dated, versioned cost model · 103 tests passing
            </p>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Phase 0</h3>
            <ul className="text-sm text-gray-600 space-y-2">
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success-600" />
                Backend skeleton (FastAPI, /health, CORS)
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success-600" />
                Configuration (session times, risk limits, cost model)
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success-600" />
                Pydantic wire schemas
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success-600" />
                Local services (docker-compose.yml, .env.example)
              </li>
              <li className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-brand-600" />
                Frontend scaffold (this page)
              </li>
            </ul>
          </div>

          <button
            onClick={() => setCount((c) => c + 1)}
            className="w-full px-4 py-2 bg-brand-600 text-white rounded-md hover:bg-brand-500 transition-colors"
          >
            Click count: {count}
          </button>
        </aside>
      </main>
    </div>
  );
}

export default App;
