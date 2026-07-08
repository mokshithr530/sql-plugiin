import ChatWidget from "./components/ChatWidget";
import "./index.css";

function App() {
  return (
    <>
      <div className="app">
        {/* Navbar */}
        <nav className="navbar">
          <div className="logo">SQL AI Plugin</div>

          <div className="nav-links">
            <a href="#">Home</a>
            <a href="#">Features</a>
            <a href="#">Documentation</a>
            <a href="#">About</a>
          </div>
        </nav>

        {/* Hero Section */}
        <section className="hero">
          <div className="hero-left">
            <h1>
              Natural Language <br />
              <span>SQL Assistant</span>
            </h1>

            <p>
              Connect your SQL database and ask questions in natural language.
              Generate SQL automatically, retrieve business insights and interact
              with your enterprise data effortlessly.
            </p>

            <button>Explore Plugin</button>
          </div>

          <div className="hero-right">
            <img
              src="https://images.unsplash.com/photo-1518770660439-4636190af475"
              alt="AI"
            />
          </div>
        </section>

        {/* Features */}
        <section className="features">
          <div className="card">
            <h3>Natural Language</h3>
            <p>Ask questions in plain English.</p>
          </div>

          <div className="card">
            <h3>Text → SQL</h3>
            <p>Automatically generates optimized SQL queries.</p>
          </div>

          <div className="card">
            <h3>Enterprise Ready</h3>
            <p>Supports SQLite, MySQL, PostgreSQL and SQL Server.</p>
          </div>
        </section>
      </div>

      {/* Floating Chat Widget */}
      <ChatWidget />
    </>
  );
}

export default App;