export default function ChatHeader() {
  return (
    <div
      className="
        bg-gradient-to-r
        from-cyan-500
        to-blue-600
        text-white
        px-5
        py-4
        border-b
      "
    >
      <h2 className="text-xl font-bold">
        Welcome to AI Plugin
      </h2>

      <p className="text-sm opacity-90 mt-1">
        Your Intelligent SQL Assistant
      </p>

      <div className="mt-4 rounded-xl bg-white/10 p-3">
        <p className="text-xs">
          👋 Upload a SQL database and ask questions in natural language.
        </p>
      </div>
    </div>
  );
}