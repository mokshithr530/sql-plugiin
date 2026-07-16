import type { ChatResponse } from "../types/chat";

export type CellValue = string | number | boolean | null | undefined | object;

export type DisplayTable = {
  columns: string[];
  rows: Record<string, unknown>[];
};

export type ResponsePresentation = {
  summary: string;
  bullets: string[];
  table: DisplayTable | null;
  limitations: string[];
};

const MONEY_WORDS = ["revenue", "price", "value", "amount", "sales", "loss", "risk"];
const COUNT_WORDS = ["count", "orders", "units", "sold", "quantity", "row_count"];

function titleize(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isMoneyColumn(column: string): boolean {
  const lower = column.toLowerCase();
  return MONEY_WORDS.some((word) => lower.includes(word));
}

function isCountColumn(column: string): boolean {
  const lower = column.toLowerCase();
  return COUNT_WORDS.some((word) => lower.includes(word));
}

export function formatCell(column: string, value: CellValue): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (isMoneyColumn(column)) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }).format(value);
    }
    if (isCountColumn(column) || Number.isInteger(value)) {
      return new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 0,
      }).format(value);
    }
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 2,
    }).format(value);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function displayColumns(columns: string[]): string[] {
  const priority = [
    "department_name",
    "employee_count",
    "project_name",
    "bill_count",
    "total_billing",
    "receivable_amount",
    "product_category",
    "product",
    "category",
    "units_sold",
    "revenue",
    "order_status",
    "affected_orders",
    "revenue_at_risk",
    "average_order_item_value",
    "average_price",
  ];
  const ordered = [
    ...priority.filter((column) => columns.includes(column)),
    ...columns.filter((column) => !priority.includes(column)),
  ];
  return ordered.slice(0, 6);
}

function extractSection(answer: string, heading: string): string[] {
  const pattern = new RegExp(`${heading}\\s*\\n([\\s\\S]*?)(?:\\n\\n[A-Z][A-Za-z ]+\\n|$)`, "i");
  const match = answer.match(pattern);
  if (!match) return [];
  return match[1]
    .split("\n")
    .map((line) => line.trim().replace(/^- /, ""))
    .filter(Boolean);
}

function summaryFromAnswer(answer: string): string {
  const summary = extractSection(answer, "Short summary")[0];
  if (summary) return summary;
  return answer.split("\n")[0] || "Here is what the data shows.";
}

export function buildResponsePresentation(response?: ChatResponse): ResponsePresentation | null {
  if (!response?.success || !response.result) return null;

  const records = Array.isArray(response.result.records)
    ? response.result.records
    : [];
  if (records.length === 0) {
    return {
      summary: response.answer || "No matching rows were found.",
      bullets: [],
      table: null,
      limitations: ["No rows were returned for this question."],
    };
  }

  const columns = displayColumns(response.result.columns || Object.keys(records[0] ?? {}));
  const first = records[0] ?? {};
  const sectionBullets = extractSection(response.answer, "Key findings");
  const bullets = sectionBullets.length > 0 ? sectionBullets : columns.slice(0, 4).map((column) => (
    `${titleize(column)}: ${formatCell(column, first[column] as CellValue)}`
  ));
  const limitations = extractSection(response.answer, "Limitations");

  return {
    summary: summaryFromAnswer(response.answer),
    bullets,
    table: records.length > 1
      ? {
          columns: ["rank", ...columns],
          rows: records.slice(0, 10).map((record, index) => ({
            rank: index + 1,
            ...record,
          })),
        }
      : null,
    limitations,
  };
}

export function labelColumn(column: string): string {
  return column === "rank" ? "Rank" : titleize(column);
}
