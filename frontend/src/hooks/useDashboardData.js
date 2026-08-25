import { useDashboardExport } from './dashboard/useDashboardExport';
import { useDashboardOverviewData } from './dashboard/useDashboardOverviewData';
import { useDashboardScraperRuntimeData } from './dashboard/useDashboardScraperRuntimeData';
import { useFeaturedSelection } from './dashboard/useFeaturedSelection';


export function useDashboardData(contentKind, activeKey) {
    const overview = useDashboardOverviewData(contentKind);
    const runtime = useDashboardScraperRuntimeData(activeKey === '2');
    const featured = useFeaturedSelection(contentKind);
    const exportState = useDashboardExport(contentKind);

    return {
        stats: overview.stats,
        spiders: runtime.spiders,
        spiderStatus: runtime.spiderStatus,
        rssSources: runtime.rssSources,
        runtimeError: runtime.runtimeError,
        overview: overview.overview,
        overviewState: overview.loadState,
        manuallyFeatured: featured.manuallyFeatured,
        setManuallyFeatured: featured.setManuallyFeatured,
        exportState,
        actions: {
            fetchStats: () => overview.refreshOverview({ includeStats: true }),
            fetchOverview: overview.refreshOverview,
            handleAddToFeatured: featured.handleAddToFeatured,
            refreshRuntime: runtime.refreshRuntime,
            ...runtime.actions,
        },
    };
}
