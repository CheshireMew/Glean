import { useEffect, useState } from 'react';
import { refreshPublicAIContent } from '../api/aiContent';

export function useAIContentRefresh(onUpdated) {
    const [requestVersion, setRequestVersion] = useState(0);
    const [update, setUpdate] = useState({ updating: false, message: '', sources: [] });

    useEffect(() => {
        let active = true;
        let timer;
        let running = false;
        const controller = new AbortController();
        const check = async () => {
            if (!active || running) return;
            clearTimeout(timer);
            if (document.visibilityState === 'hidden') {
                timer = setTimeout(check, 30000);
                return;
            }
            running = true;
            let delay = 30000;
            try {
                const response = await refreshPublicAIContent({ signal: controller.signal });
                if (!active) return;
                setUpdate(response.data);
                onUpdated();
                if (response.data.updating) delay = 3000;
            } catch (error) {
                if (!active) return;
                setUpdate({ updating: false, message: error.message || '自动更新暂时失败，稍后会重试。', sources: [] });
            } finally {
                running = false;
                if (active) timer = setTimeout(check, delay);
            }
        };
        const resume = () => {
            if (document.visibilityState !== 'hidden') check();
        };
        check();
        document.addEventListener('visibilitychange', resume);
        window.addEventListener('online', resume);
        return () => {
            active = false;
            controller.abort();
            clearTimeout(timer);
            document.removeEventListener('visibilitychange', resume);
            window.removeEventListener('online', resume);
        };
    }, [onUpdated, requestVersion]);

    return { update, refreshNow: () => setRequestVersion((value) => value + 1) };
}
