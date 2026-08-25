import { useCallback, useEffect, useState } from 'react';

import { getPublicSiteConfig } from '../../api/content';

const EMPTY_CONFIG = Object.freeze({ site_url: '', links: {} });

export function usePublicSiteConfig() {
    const [config, setConfig] = useState(EMPTY_CONFIG);

    const load = useCallback(async () => {
        try {
            const response = await getPublicSiteConfig();
            if (response.data?.links && typeof response.data.links === 'object') {
                setConfig(response.data);
            }
        } catch {
            setConfig(EMPTY_CONFIG);
        }
    }, []);

    useEffect(() => {
        const timer = window.setTimeout(() => { void load(); }, 0);
        return () => window.clearTimeout(timer);
    }, [load]);

    return config;
}
