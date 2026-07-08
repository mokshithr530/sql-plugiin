export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  success: boolean;
  answer: string;
  sql?: string;
  result?: {
    rows: number;
    columns: string[];
    records: Record<string, unknown>[];
  } | null;
  error?: string;
}
