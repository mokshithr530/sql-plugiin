import { Database, CheckCircle2, X } from "lucide-react";

interface DatabaseChipProps {
  databaseName: string;
  databaseType?: string;
  tables?: number;
  columns?: number;
  onRemove?: () => void;
}

export default function DatabaseChip({
  databaseName,
  databaseType = "SQLite",
  tables,
  columns,
  onRemove,
}: DatabaseChipProps) {
  if (!databaseName) return null;

  return (
    <div
      className="
        mb-3
        flex
        items-center
        justify-between
        rounded-2xl
        border
        border-cyan-200
        bg-cyan-50
        p-3
        shadow-sm
      "
    >
      <div className="flex items-center gap-3">
        <div
          className="
            flex
            h-10
            w-10
            items-center
            justify-center
            rounded-xl
            bg-cyan-500
            text-white
          "
        >
          <Database size={20} />
        </div>

        <div>
          <div className="flex items-center gap-2">
            <CheckCircle2
              size={16}
              className="text-green-600"
            />

            <span className="font-semibold text-gray-800">
              {databaseName}
            </span>
          </div>

          <p className="text-xs text-gray-500">
            {databaseType}

            {tables !== undefined &&
              columns !== undefined &&
              ` • ${tables} Tables • ${columns} Columns`}
          </p>
        </div>
      </div>

      {onRemove && (
        <button
          onClick={onRemove}
          className="
            rounded-full
            p-1
            hover:bg-gray-200
            transition
          "
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}