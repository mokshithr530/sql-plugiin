import { useEffect, useRef } from "react";
import type { Message } from "../types/chat";
import MetricsDisplay from "./MetricsDisplay";

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
              className={`max-w-[88%] rounded-lg border px-3.5 py-2.5 whitespace-pre-wrap text-sm leading-6 ${
                message.role === "user"
                  ? "border-gray-950 bg-gray-950 text-white"
                  : "border-gray-200 bg-white text-gray-800"
              }`}
            >
              {message.content}
            </div>
          </div>
          {message.role === "assistant" && message.metrics && (
            <div className="mt-2 ml-0 flex justify-start">
              <div className="max-w-[88%]">
                <MetricsDisplay metrics={message.metrics} />
              </div>
            </div>
          )}
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
