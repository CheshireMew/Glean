import contract from '@shared-content-contract';

export const CONTENT_KIND = Object.freeze({
    NEWS: contract.contentKinds.news,
    ARTICLE: contract.contentKinds.article,
});

export const REVIEW_DECISION = Object.freeze({
    SELECTED: contract.review.statuses.selected,
    DISCARDED: contract.review.statuses.discarded,
});

export const ENRICHMENT_STATUS = Object.freeze({
    PENDING: contract.enrichment.statuses.pending,
    PROCESSING: contract.enrichment.statuses.processing,
    COMPLETED: contract.enrichment.statuses.completed,
    FAILED: contract.enrichment.statuses.failed,
    NOT_APPLICABLE: contract.enrichment.statuses.notApplicable,
});

export const EXPORT_SCOPE = Object.freeze({
    INCOMING: contract.exportScopes.incoming,
    ARCHIVE: contract.exportScopes.archive,
    BLOCKED: contract.exportScopes.blocked,
    REVIEW: contract.exportScopes.review,
    SELECTED: contract.exportScopes.selected,
    DISCARDED: contract.exportScopes.discarded,
});

export const PUBLIC_STREAM = Object.freeze({
    BRIEFS: contract.publicStreams.briefs,
    LONGFORM: contract.publicStreams.longform,
});

export const FEED_TAB = Object.freeze({
    LONGFORM: PUBLIC_STREAM.LONGFORM,
    BRIEFS: PUBLIC_STREAM.BRIEFS,
    ARTICLE_REPORTS: 'article-reports',
    BRIEF_REPORTS: 'brief-reports',
});

export const NEWSFEED_TABS = [
    { key: FEED_TAB.LONGFORM, label: '文章' },
    { key: FEED_TAB.BRIEFS, label: '快讯' },
    { key: FEED_TAB.ARTICLE_REPORTS, label: '文章日报' },
    { key: FEED_TAB.BRIEF_REPORTS, label: '快讯日报' },
];

export const DASHBOARD_OVERVIEW_KEYS = [
    EXPORT_SCOPE.INCOMING,
    EXPORT_SCOPE.ARCHIVE,
    EXPORT_SCOPE.BLOCKED,
    EXPORT_SCOPE.REVIEW,
    EXPORT_SCOPE.SELECTED,
    EXPORT_SCOPE.DISCARDED,
];

export const DEFAULT_DASHBOARD_OVERVIEW = Object.fromEntries(
    DASHBOARD_OVERVIEW_KEYS.map((key) => [key, 0]),
);

export const DASHBOARD_EXPORT_OPTIONS = [
    { value: EXPORT_SCOPE.INCOMING, label: '采集池' },
    { value: EXPORT_SCOPE.ARCHIVE, label: '归档池' },
    { value: EXPORT_SCOPE.BLOCKED, label: '已拦截' },
    { value: EXPORT_SCOPE.REVIEW, label: '待审核' },
    { value: EXPORT_SCOPE.SELECTED, label: '已选入' },
    { value: EXPORT_SCOPE.DISCARDED, label: '已舍弃' },
];
