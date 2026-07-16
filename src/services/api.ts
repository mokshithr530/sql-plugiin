import type { ChatResponse } from "../types/chat";
import type { UploadResponse } from "../types/database";
import { getSessionId } from "./session";

const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

type ApiErrorResponse = {
    success?: false;
    detail?: string;
    message?: string;
};

async function readJsonResponse<T>(response: Response): Promise<T> {
    const data = await response.json().catch(() => null);

    if (!response.ok) {
        const message =
            data?.detail ??
            data?.message ??
            `Request failed with status ${response.status}`;

        throw new Error(message);
    }

    return data as T;
}

export async function uploadDatabase(file: File): Promise<UploadResponse & ApiErrorResponse> {

    const formData = new FormData();

    formData.append("file", file);
    formData.append("session_id", getSessionId());

    const response = await fetch(`${API}/upload`, {

        method: "POST",

        body: formData

    });

    return readJsonResponse<UploadResponse & ApiErrorResponse>(response);
}

export async function listMySQLDatabases(): Promise<{ success: boolean; databases: string[] }> {
    const response = await fetch(`${API}/mysql/databases`);

    return readJsonResponse<{ success: boolean; databases: string[] }>(response);
}

export async function attachMySQLDatabase(database: string): Promise<UploadResponse & ApiErrorResponse> {
    const response = await fetch(`${API}/mysql/attach`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            database,
            session_id: getSessionId()
        })
    });

    return readJsonResponse<UploadResponse & ApiErrorResponse>(response);
}

export async function sendMessage(question: string): Promise<ChatResponse> {

    const response = await fetch(`${API}/chat`, {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            question,
            session_id: getSessionId()
        })

    });

    return readJsonResponse<ChatResponse>(response);
}

export async function getStatus() {

    const response = await fetch(
        `${API}/status?session_id=${encodeURIComponent(getSessionId())}`
    );

    return readJsonResponse(response);
}

export async function clearSession() {

    const response = await fetch(`${API}/clear`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            session_id: getSessionId()
        })
    });

    return readJsonResponse(response);
}
