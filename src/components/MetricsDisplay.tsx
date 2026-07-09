import type { TokenMetrics } from "../types/chat";

interface MetricsDisplayProps {
  metrics: TokenMetrics | undefined;
}

export default function MetricsDisplay({ metrics }: MetricsDisplayProps) {
  if (!metrics) return null;

  // Calculate estimated cost (Gemini flash-lite pricing)
  // Input: $0.075 per 1M tokens, Output: $0.3 per 1M tokens
  const inputCost = (metrics.input_tokens / 1000000) * 0.075;
  const outputCost = (metrics.output_tokens / 1000000) * 0.3;
  const totalCost = inputCost + outputCost;
  const costInRupees = totalCost * 83; // 1 USD = 83 INR

  return (
    <div
      className="
        mt-2
        p-3
        bg-blue-50
        border
        border-blue-200
        rounded-lg
        text-xs
        text-gray-700
      "
    >
      <div className="font-semibold text-blue-900 mb-2">
        ⚡ Token Metrics
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <span className="text-gray-600">Input Tokens:</span>
          <span className="ml-1 font-mono font-semibold">
            {metrics.input_tokens.toLocaleString()}
          </span>
        </div>
        <div>
          <span className="text-gray-600">Output Tokens:</span>
          <span className="ml-1 font-mono font-semibold">
            {metrics.output_tokens.toLocaleString()}
          </span>
        </div>
      </div>

      <div className="mb-2">
        <span className="text-gray-600">Total Tokens:</span>
        <span className="ml-1 font-mono font-semibold text-lg">
          {metrics.total_tokens.toLocaleString()}
        </span>
      </div>

      <div className="mb-2">
        <span className="text-gray-600">API Calls:</span>
        <span className="ml-1 font-mono font-semibold">
          {metrics.api_calls_count}
        </span>
      </div>

      <div className="mb-3">
        <span className="text-gray-600">Time:</span>
        <span className="ml-1 font-mono font-semibold">
          {metrics.elapsed_seconds?.toFixed(2)}s
        </span>
      </div>

      {/* Cost estimation */}
      <div className="pt-2 border-t border-blue-200">
        <div className="text-gray-600 mb-1">Estimated Cost:</div>
        <div className="font-mono font-semibold text-green-700">
          ${totalCost.toFixed(6)} / ₹{costInRupees.toFixed(2)}
        </div>
      </div>

      {/* API calls breakdown */}
      {metrics.api_calls.length > 0 && (
        <div className="pt-2 border-t border-blue-200 mt-2">
          <div className="text-gray-600 font-semibold mb-1">
            API Calls Breakdown:
          </div>
          <div className="space-y-1">
            {metrics.api_calls.map((call, index) => (
              <div
                key={index}
                className="text-gray-700 flex justify-between"
              >
                <span>{call.type}:</span>
                <span className="font-mono">
                  {call.total_tokens} tokens ({call.input_tokens} in,{" "}
                  {call.output_tokens} out)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
