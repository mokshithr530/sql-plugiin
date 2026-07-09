import { useState } from "react";

import { sendMessage } from "../services/api";

import type { Message } from "../types/chat";

export function useChat() {

    const [messages, setMessages] = useState<Message[]>([
        {
            role: "assistant",
            content:
                "Upload a SQL database to begin."
        }
    ]);

    const [loading, setLoading] = useState(false);

    async function ask(question: string) {
        if (!question.trim()) return;

        setMessages(prev => [
            ...prev,
            {
                role: "user",
                content: question
            }
        ]);

        setLoading(true);

        try {
            const response = await sendMessage(question);

            setMessages(prev => [
                ...prev,
                {
                    role: "assistant",
                    content: response.success
                        ? response.answer
                        : `${response.answer}\n\nYou can also try asking the same question with more specific table or column words.`,
                    metrics: response.metrics
                }
            ]);
        } catch (err) {
            setMessages(prev => [
                ...prev,
                {
                    role: "assistant",
                    content:
                        err instanceof Error
                            ? err.message
                            : "Something went wrong while asking the database."
                }
            ]);
        } finally {
            setLoading(false);
        }
    }

    return {

        messages,

        loading,

        ask

    };

}
