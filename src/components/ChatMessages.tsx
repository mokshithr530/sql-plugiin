import { useEffect, useRef } from "react";
import type { Message } from "../types/chat";

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
        bg-gray-50
        px-4
        py-5
        space-y-4
      "
    >
      {messages.map((message, index) => (
        <div
          key={index}
          className={`flex ${
            message.role === "user"
              ? "justify-end"
              : "justify-start"
          }`}
        >
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-md whitespace-pre-wrap text-sm leading-6 ${
              message.role === "user"
                ? "bg-cyan-500 text-white"
                : "bg-white text-gray-800"
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}

      {loading && (
        <div className="flex justify-start">
          <div
            className="
              bg-white
              rounded-2xl
              px-4
              py-3
              shadow-md
              flex
              items-center
              gap-2
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
