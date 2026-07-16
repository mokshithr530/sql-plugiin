import { useRef, useState } from "react";
import { Database } from "lucide-react";

import { attachMySQLDatabase, listMySQLDatabases, uploadDatabase } from "../services/api";
import type { DatabaseInfo } from "../types/database";

interface UploadDatabaseProps {
  onUploadSuccess: (database: DatabaseInfo) => void;
}

export default function UploadDatabase({
  onUploadSuccess,
}: UploadDatabaseProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const [uploading, setUploading] = useState(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"upload" | "connect">("upload");
  const [uploadingFileType, setUploadingFileType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [databases, setDatabases] = useState<string[]>([]);
  const [selectedDatabase, setSelectedDatabase] = useState("");
  const [loadingDatabases, setLoadingDatabases] = useState(false);

  const handleUpload = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];

    if (!file) return;

    setUploading(true);
    setUploadingFileType(file.name.toLowerCase().endsWith(".sql") ? "sql" : "database");
    setError(null);

    try {
      const result = await uploadDatabase(file);

      if (result.success && result.database) {
        onUploadSuccess(result.database);
        setOpen(false);
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
      setUploadingFileType(null);
    }
  };

  const loadDatabases = async () => {
    setLoadingDatabases(true);
    setError(null);
    try {
      const result = await listMySQLDatabases();
      setDatabases(result.databases);
      setSelectedDatabase(result.databases[0] ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to list MySQL databases.");
    } finally {
      setLoadingDatabases(false);
    }
  };

  const connectDatabase = async () => {
    if (!selectedDatabase) return;
    setUploading(true);
    setError(null);
    try {
      const result = await attachMySQLDatabase(selectedDatabase);
      if (result.success && result.database) {
        onUploadSuccess(result.database);
        setOpen(false);
      } else {
        setError(result.detail ?? "Unable to connect database.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect database.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <div className="relative">
        <button
          onClick={() => {
            setOpen((value) => !value);
            if (!open && mode === "connect") void loadDatabases();
          }}
          disabled={uploading}
          title="Upload database"
          className="
            h-11
            w-11
            rounded-lg
            border
            border-gray-300
            bg-white
            hover:bg-gray-100
            disabled:cursor-not-allowed
            disabled:opacity-60
            transition-colors
            flex
            items-center
            justify-center
            text-gray-700
          "
        >
          <Database size={20} />
        </button>

        {open && (
          <div
            className="
              absolute
              bottom-13
              left-0
              z-20
              w-72
              rounded-lg
              border
              border-gray-200
              bg-white
              px-3
              py-3
              text-xs
              text-gray-700
              shadow-lg
            "
          >
            <div className="mb-3 grid grid-cols-2 gap-1 rounded-lg bg-gray-100 p-1">
              <button
                type="button"
                onClick={() => setMode("upload")}
                className={`rounded-md px-2 py-1.5 ${mode === "upload" ? "bg-white shadow-sm" : ""}`}
              >
                Upload SQL Dump
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("connect");
                  void loadDatabases();
                }}
                className={`rounded-md px-2 py-1.5 ${mode === "connect" ? "bg-white shadow-sm" : ""}`}
              >
                Connect Existing
              </button>
            </div>

            {mode === "upload" ? (
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={uploading}
                className="w-full rounded-lg bg-gray-950 px-3 py-2 text-sm text-white disabled:opacity-60"
              >
                Choose file
              </button>
            ) : (
              <div className="space-y-2">
                <select
                  value={selectedDatabase}
                  onChange={(event) => setSelectedDatabase(event.target.value)}
                  disabled={loadingDatabases || uploading}
                  className="w-full rounded-lg border border-gray-300 px-2 py-2 text-sm"
                >
                  {databases.map((database) => (
                    <option key={database} value={database}>
                      {database}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={connectDatabase}
                  disabled={!selectedDatabase || uploading || loadingDatabases}
                  className="w-full rounded-lg bg-gray-950 px-3 py-2 text-sm text-white disabled:opacity-60"
                >
                  {loadingDatabases ? "Loading..." : "Connect"}
                </button>
              </div>
            )}

            {error && (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 leading-5 text-red-700">
                {error}
              </div>
            )}
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        hidden
        type="file"
        accept=".db,.sqlite,.sqlite3,.sql"
        onChange={handleUpload}
      />

      {uploading && (
        <div
          className="
            fixed
            inset-0
            bg-black/30
            flex
            items-center
            justify-center
            z-[999]
          "
        >
          <div
            className="
              bg-white
              rounded-lg
              p-6
              shadow-xl
              text-center
            "
          >
            <div
              className="
                h-10
                w-10
                rounded-full
                border-[3px]
                border-gray-950
                border-t-transparent
                animate-spin
                mx-auto
              "
            />

            <p className="mt-4 text-sm text-gray-700">
              {uploadingFileType === "sql"
                ? "Preparing database -> Importing..."
                : "Uploading database..."}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
