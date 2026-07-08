import { useState } from "react";
import { MessageCircle, X } from "lucide-react";

import ChatHeader from "./ChatHeader";
import ChatMessages from "./ChatMessages";
import ChatInput from "./ChatInput";

import type { DatabaseInfo } from "../types/database";
import { useChat } from "../hooks/useChat";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [database, setDatabase] = useState<DatabaseInfo | null>(null);
  const { messages, loading, ask } = useChat();

  return (
    <>
      {/* Floating Button */}

      <button
        onClick={() => setOpen(!open)}
        className="
        fixed
        bottom-6
        right-6
        h-16
        w-16
        rounded-full
        bg-gradient-to-r
        from-cyan-500
        to-blue-600
        text-white
        shadow-xl
        flex
        items-center
        justify-center
        hover:scale-110
        transition-all
        duration-300
        z-50
      "
      >
        {open ? <X size={30} /> : <MessageCircle size={30} />}
      </button>

      {/* Widget */}

      <div
        className={`
        fixed
        bottom-24
        right-6
        w-[390px]
        h-[650px]
        rounded-3xl
        bg-white
        shadow-[0_15px_45px_rgba(0,0,0,0.18)]
        overflow-hidden
        transition-all
        duration-300
        origin-bottom-right
        flex
        flex-col

        ${
          open
            ? "opacity-100 scale-100"
            : "opacity-0 scale-95 pointer-events-none"
        }
      `}
      >
        <ChatHeader />

        <ChatMessages
          messages={messages}
          loading={loading}
        />
            
        <ChatInput
          onSend={ask}
          database={database}
          setDatabase={setDatabase}
        />
      </div>
    </>
  );
}
