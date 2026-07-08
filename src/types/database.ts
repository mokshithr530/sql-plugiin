export interface DatabaseInfo {
  name: string;
  type: string;
  tables: number;
  columns: number;
}

export interface UploadResponse {
  success: boolean;
  database: DatabaseInfo;
  message: string;
}
