import { useRef, useState } from 'react';
import dayjs from 'dayjs';
import { message } from 'antd';

import { listReviewedContent } from '../../api/content';
import { ENRICHMENT_STATUS, REVIEW_DECISION } from '../../contracts/content';
import { getRequestErrorMessage } from './listStateHelpers';
import { parseUtcTimestamp } from '../../utils/time';

export function useExportItems(contentKind, manuallyFeatured) {
    const [exportTimeRange, setExportTimeRange] = useState(24);
    const [exportMinScore, setExportMinScore] = useState(6);
    const [selectedPools, setSelectedPools] = useState({ news: [], article: [] });
    const [loadingByKind, setLoadingByKind] = useState({ news: false, article: false });
    const requestIdsRef = useRef({ news: 0, article: 0 });
    const selectedPool = selectedPools[contentKind] || [];
    const loading = Boolean(loadingByKind[contentKind]);

    const visibleItems = [
        ...manuallyFeatured.map((item) => ({ ...item, isFeatured: true })),
        ...selectedPool.filter((item) => !manuallyFeatured.some((manual) => manual.outputKey === item.outputKey)),
    ];

    const loadItems = async () => {
        const requestKind = contentKind;
        const requestId = (requestIdsRef.current[requestKind] || 0) + 1;
        requestIdsRef.current[requestKind] = requestId;
        try {
            setLoadingByKind((previous) => ({ ...previous, [requestKind]: true }));
            const allItems = [];
            let page = 1;
            let total = 0;
            do {
                const res = await listReviewedContent({
                    decision: REVIEW_DECISION.SELECTED,
                    page,
                    limit: 200,
                    kind: requestKind,
                });
                const pageItems = res.data.data || [];
                if (pageItems.length === 0) break;
                allItems.push(...pageItems);
                total = Number(res.data.total || pageItems.length);
                page += 1;
            } while (allItems.length < total);
            const cutoff = dayjs().subtract(exportTimeRange, 'hour').valueOf();
            const eligibleItems = allItems.filter(
                (item) => item.enrichment_status === ENRICHMENT_STATUS.COMPLETED,
            );
            const nextItems = eligibleItems.filter((item) => {
                const score = item.review_score ?? 0;
                return score >= exportMinScore && parseUtcTimestamp(item.published_at).getTime() > cutoff;
            });
            if (requestIdsRef.current[requestKind] !== requestId) return;
            setSelectedPools((previous) => ({
                ...previous,
                [requestKind]: nextItems.map((item) => ({
                    ...item,
                    outputRef: { scope: 'selected', id: Number(item.id) },
                    outputKey: `selected:${item.id}`,
                })),
            }));
            const waitingCount = allItems.length - eligibleItems.length;
            message.success(
                waitingCount > 0
                    ? `加载了 ${nextItems.length} 条可交付内容，另有 ${waitingCount} 条仍在生成深度内容`
                    : `加载了 ${nextItems.length} 条内容`,
            );
        } catch (error) {
            if (requestIdsRef.current[requestKind] !== requestId) return;
            message.error(`加载失败: ${getRequestErrorMessage(error, '加载失败')}`);
        } finally {
            if (requestIdsRef.current[requestKind] === requestId) {
                setLoadingByKind((previous) => ({ ...previous, [requestKind]: false }));
            }
        }
    };

    return {
        exportTimeRange,
        exportMinScore,
        visibleItems,
        loading,
        setExportTimeRange,
        setExportMinScore,
        loadItems,
    };
}
