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
        h-14
        w-14
        rounded-lg
        bg-gray-950
        text-white
        shadow-lg
        flex
        items-center
        justify-center
        hover:bg-gray-800
        transition-all
        duration-150
        z-50
      "
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>

      {/* Widget */}

      <div
        className={`
        fixed
        bottom-24
        right-6
        w-[390px]
        max-w-[calc(100vw-2rem)]
        h-[620px]
        max-h-[calc(100vh-7rem)]
        rounded-lg
        bg-white
        border
        border-gray-200
        shadow-2xl
        overflow-hidden
        transition-all
        duration-150
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
