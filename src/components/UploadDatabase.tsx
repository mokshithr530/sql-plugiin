import { useRef, useState } from "react";
import { Database } from "lucide-react";

import { uploadDatabase } from "../services/api";
import type { DatabaseInfo } from "../types/database";

interface UploadDatabaseProps {
  onUploadSuccess: (database: DatabaseInfo) => void;
}

export default function UploadDatabase({
  onUploadSuccess,
}: UploadDatabaseProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];

    if (!file) return;

    setUploading(true);
    setError(null);

    try {
      const result = await uploadDatabase(file);

      if (result.success && result.database) {
        onUploadSuccess(result.database);
      } else {
        setError(result.detail ?? "Unable to upload database.");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to upload database."
      );
      console.error(err);
    } finally {
      setUploading(false);

      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  };

  return (
    <>
      <div className="relative">
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          title="Upload database"
          className="
            h-11
            w-11
            rounded-full
            bg-gray-100
            hover:bg-cyan-100
            disabled:cursor-not-allowed
            disabled:opacity-60
            transition
            flex
            items-center
            justify-center
          "
        >
          <Database size={20} />
        </button>

        {error && (
          <div
            className="
              absolute
              bottom-13
              left-0
              z-20
              w-64
              rounded-lg
              border
              border-red-200
              bg-red-50
              px-3
              py-2
              text-xs
              leading-5
              text-red-700
              shadow-lg
            "
          >
            {error}
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        hidden
        type="file"
        accept=".db,.sqlite,.sql"
        onChange={handleUpload}
      />

      {uploading && (
        <div
          className="
            fixed
            inset-0
            bg-black/40
            flex
            items-center
            justify-center
            z-[999]
          "
        >
          <div
            className="
              bg-white
              rounded-2xl
              p-8
              shadow-xl
              text-center
            "
          >
            <div
              className="
                h-10
                w-10
                rounded-full
                border-4
                border-cyan-500
                border-t-transparent
                animate-spin
                mx-auto
              "
            />

            <p className="mt-5">
              Uploading database...
            </p>
          </div>
        </div>
      )}
    </>
  );
}
