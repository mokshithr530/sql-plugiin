import ChatWidget from "./components/ChatWidget";
import "./index.css";

function App() {
  return (
    <>
      <div className="min-h-screen bg-gray-100 text-gray-950">
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <div>
              <div className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">
                SQL Assistant
              </div>
              <h1 className="mt-1 text-2xl font-semibold">
                Natural language database querying
              </h1>
            </div>

            <div className="hidden rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 sm:block">
              Backend ready
            </div>
          </div>
        </header>

        <main className="mx-auto grid max-w-6xl gap-4 px-6 py-6 md:grid-cols-[1.4fr_0.8fr]">
          <section className="rounded-lg border border-gray-200 bg-white p-5">
            <h2 className="text-lg font-semibold">
              POC workspace
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
              Upload a SQLite database from the chat widget, ask a question,
              and the backend will generate, validate, execute, and explain the
              SQL result.
            </p>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {["Upload database", "Ask question", "Review answer"].map(
                (item, index) => (
                  <div
                    key={item}
                    className="rounded-lg border border-gray-200 bg-gray-50 p-4"
                  >
                    <div className="text-xs font-semibold text-gray-500">
                      Step {index + 1}
                    </div>
                    <div className="mt-1 text-sm font-medium">
                      {item}
                    </div>
                  </div>
                )
              )}
            </div>
          </section>

          <aside className="rounded-lg border border-gray-200 bg-white p-5">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-gray-500">
              Supported files
            </h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {[".db", ".sqlite", ".sql"].map((type) => (
                <span
                  key={type}
                  className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium"
                >
                  {type}
                </span>
              ))}
            </div>

            <p className="mt-5 text-sm leading-6 text-gray-600">
              The frontend stays provider-neutral. The backend decides which
              LLM provider to use through environment configuration.
            </p>
          </aside>
        </main>
      </div>

      <ChatWidget />
    </>
  );
}

export default App;
