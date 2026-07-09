export interface Message {
  role: "user" | "assistant";
  content: string;
  metrics?: TokenMetrics;
}

export interface TokenMetrics {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  api_calls_count: number;
  elapsed_seconds: number;
  api_calls: ApiCall[];
}

export interface ApiCall {
  type: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  timestamp: string;
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
  metrics?: TokenMetrics;
}
