export interface Message {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
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
  confidence?: Confidence;
}

export interface Confidence {
  confidence_score: number;
  confidence_level: "high" | "medium" | "low";
  confidence_reasons: string[];
  limitations: string[];
}
