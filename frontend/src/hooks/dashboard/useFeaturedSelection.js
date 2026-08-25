import { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';


const storageKey = (contentKind) => `ainews.output-draft.${contentKind}`;
const EMPTY_DRAFT = [];

const readDraft = (contentKind) => {
    try {
        const value = JSON.parse(localStorage.getItem(storageKey(contentKind)) || '[]');
        return Array.isArray(value) ? value : [];
    } catch {
        return [];
    }
};

export function useFeaturedSelection(contentKind) {
    const [drafts, setDrafts] = useState(() => ({
        news: readDraft('news'),
        article: readDraft('article'),
    }));
    const manuallyFeatured = drafts[contentKind] || EMPTY_DRAFT;
    const setManuallyFeatured = useCallback((nextValue) => {
        setDrafts((previous) => {
            const current = previous[contentKind] || [];
            const next = typeof nextValue === 'function' ? nextValue(current) : nextValue;
            return { ...previous, [contentKind]: next };
        });
    }, [contentKind]);

    useEffect(() => {
        localStorage.setItem(storageKey(contentKind), JSON.stringify(manuallyFeatured));
    }, [contentKind, manuallyFeatured]);

    const handleAddToFeatured = useCallback((record, scope) => {
        const outputRef = { scope, id: Number(record.id) };
        const outputKey = `${scope}:${record.id}`;
        setManuallyFeatured((previous) => {
            if (previous.some((item) => item.outputKey === outputKey)) {
                message.warning('此内容已在输出列表中');
                return previous;
            }
            message.success('已加入输出列表');
            return [{ ...record, outputRef, outputKey }, ...previous];
        });
    }, [setManuallyFeatured]);

    return {
        manuallyFeatured,
        setManuallyFeatured,
        handleAddToFeatured,
    };
}
