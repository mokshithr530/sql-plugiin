import { useEffect, useRef } from "react";
import type { Message } from "../types/chat";
import {
  buildResponsePresentation,
  type CellValue,
  formatCell,
  labelColumn,
} from "../utils/responsePresentation";

interface ChatMessagesProps {
  messages: Message[];
  loading: boolean;
}

export default function ChatMessages({
  messages,
  loading,
}: ChatMessagesProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  function renderAssistantMessage(message: Message) {
    const presentation = buildResponsePresentation(message.response);
    const confidence = message.response?.confidence;

    if (!presentation) {
      return (
        <div className="space-y-3">
          <div className="whitespace-pre-wrap">{message.content}</div>
          {confidence && renderConfidence(confidence)}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <p>{presentation.summary}</p>

        {presentation.table && (
          <div className="overflow-x-auto rounded-md border border-gray-200">
            <table className="min-w-full border-collapse text-left text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  {presentation.table.columns.map((column) => (
                    <th key={column} className="px-3 py-2 font-semibold">
                      {labelColumn(column)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {presentation.table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-t border-gray-100">
                    {presentation.table?.columns.map((column) => (
                      <td key={column} className="px-3 py-2 text-gray-800">
                        {formatCell(column, row[column] as CellValue)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!presentation.table && presentation.bullets.length > 0 && (
          <ul className="list-disc space-y-1 pl-5">
            {presentation.bullets.slice(0, 5).map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        )}

        {presentation.limitations.length > 0 && (
          <details className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <summary className="cursor-pointer text-xs font-semibold text-gray-600">
              Limitations
            </summary>
            <div className="mt-2 space-y-1 text-xs text-gray-600">
              {presentation.limitations.map((limitation) => (
                <p key={limitation}>{limitation}</p>
              ))}
            </div>
          </details>
        )}

        {message.response?.sql && (
          <details className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <summary className="cursor-pointer text-xs font-semibold text-gray-600">
              SQL details
            </summary>
            <pre className="mt-2 overflow-x-auto text-xs leading-5 text-gray-700">
              {message.response.sql}
            </pre>
          </details>
        )}

        {confidence && renderConfidence(confidence)}
      </div>
    );
  }

  function renderConfidence(confidence: NonNullable<Message["response"]>["confidence"]) {
    if (!confidence) return null;
    const levelStyles = {
      high: "border-emerald-200 bg-emerald-50 text-emerald-800",
      medium: "border-amber-200 bg-amber-50 text-amber-800",
      low: "border-red-200 bg-red-50 text-red-800",
    }[confidence.confidence_level];

    return (
      <div className={`rounded-md border px-3 py-2 text-xs ${levelStyles}`}>
        <div className="flex items-center justify-between gap-3">
          <span className="font-semibold capitalize">
            {confidence.confidence_level} confidence
          </span>
          <span className="font-mono">{confidence.confidence_score}%</span>
        </div>
        <details className="mt-1">
          <summary className="cursor-pointer font-medium">Why?</summary>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {confidence.confidence_reasons.slice(0, 4).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          {confidence.limitations.length > 0 && (
            <div className="mt-2">
              <div className="font-medium">Limitations</div>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {confidence.limitations.slice(0, 3).map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </div>
          )}
        </details>
      </div>
    );
  }

  return (
    <div
      className="
        flex-1
        overflow-y-auto
        bg-gray-100
        px-4
        py-4
        space-y-3
      "
    >
      {messages.map((message, index) => (
        <div key={index}>
          <div
            className={`flex ${
              message.role === "user"
                ? "justify-end"
                : "justify-start"
            }`}
          >
            <div
              className={`max-w-[88%] rounded-lg border px-3.5 py-2.5 text-sm leading-6 ${
                message.role === "user"
                  ? "border-gray-950 bg-gray-950 text-white"
                  : "border-gray-200 bg-white text-gray-800"
              }`}
            >
              {message.role === "assistant"
                ? renderAssistantMessage(message)
                : message.content}
            </div>
          </div>
        </div>
      ))}

      {loading && (
        <div className="flex justify-start">
          <div
            className="
              bg-white
              rounded-lg
              border
              border-gray-200
              px-3
              py-2
              flex
              items-center
              gap-2
              text-gray-500
            "
          >
            <span className="animate-bounce">●</span>
            <span
              className="animate-bounce"
              style={{ animationDelay: "0.2s" }}
            >
              ●
            </span>
            <span
              className="animate-bounce"
              style={{ animationDelay: "0.4s" }}
            >
              ●
            </span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
