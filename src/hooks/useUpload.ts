import { useState } from "react";

import { uploadDatabase } from "../services/api";
import type { DatabaseInfo } from "../types/database";

export function useUpload() {

    const [loading, setLoading] = useState(false);
    const [database, setDatabase] = useState<DatabaseInfo | null>(null);

    const upload = async (file: File) => {

        setLoading(true);

        const result = await uploadDatabase(file);

        if (result.success) {

            setDatabase(result.database);

        }

        return result;
    };

    return {

        upload,

        loading,

        database

    };

}
