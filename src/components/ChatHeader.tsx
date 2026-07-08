export default function ChatHeader() {
  return (
    <div
      className="
        bg-white
        px-4
        py-3
        border-b
        border-gray-200
      "
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-950">
            SQL Assistant
          </h2>

          <p className="mt-0.5 text-xs text-gray-500">
            Query uploaded databases in natural language
          </p>
        </div>

        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
          Online
        </span>
      </div>
    </div>
  );
}
