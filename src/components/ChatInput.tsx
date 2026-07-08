import { useState } from "react";
import { Send } from "lucide-react";

import UploadDatabase from "./UploadDatabase";
import DatabaseChip from "./DatabaseChip";

import type { DatabaseInfo } from "../types/database";

interface ChatInputProps {
  onSend: (message: string) => void;

  database: DatabaseInfo | null;

  setDatabase: React.Dispatch<
    React.SetStateAction<DatabaseInfo | null>
  >;
}

export default function ChatInput({
  onSend,
  database,
  setDatabase,
}: ChatInputProps) {
  const [message, setMessage] = useState("");

  const handleSend = () => {
    if (!message.trim()) return;

    onSend(message);

    setMessage("");
  };

  return (
    <div className="border-t border-gray-200 bg-white p-3">

      {/* Attached Database */}

      {database && (
        <DatabaseChip
          databaseName={database.name}
          databaseType={database.type}
          tables={database.tables}
          columns={database.columns}
          onRemove={() => setDatabase(null)}
        />
      )}

      <div className="flex items-center gap-2">

        {!database && (
          <UploadDatabase
            onUploadSuccess={(db) => {
              setDatabase(db);
            }}
          />
        )}

        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              handleSend();
            }
          }}
          placeholder={
            database
              ? "Ask anything about your database..."
              : "Upload a database to start asking questions..."
          }
          className="
            flex-1
            rounded-lg
            border
            border-gray-300
            px-3
            py-2.5
            text-sm
            outline-none
            focus:border-gray-950
          "
        />

        <button
          onClick={handleSend}
          className="
            h-11
            w-11
            rounded-lg
            bg-gray-950
            hover:bg-gray-800
            text-white
            flex
            items-center
            justify-center
            transition-colors
          "
        >
          <Send size={18} />
        </button>

      </div>
    </div>
  );
}
