export interface DatabaseInfo {
  name: string;
  type: string;
  tables: number;
  columns: number;
  source_type?: string;
  connection_id?: string;
  already_imported?: boolean;
  import_method?: string;
  import_duration_seconds?: number;
  progress?: string[];
}

export interface UploadResponse {
  success: boolean;
  database: DatabaseInfo;
  message: string;
}
