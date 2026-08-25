export const API_RESOURCE = Object.freeze({
    CONTENT_OVERVIEW: 'content-overview',
    CONTENT_LISTS: 'content-lists',
    DELIVERY_OPERATIONS: 'delivery-operations',
    SCRAPER_RUNTIME: 'scraper-runtime',
    EDITORIAL_WORKBENCH: 'editorial-workbench',
    AI_QUALITY: 'ai-quality',
    PUBLICATIONS: 'publications',
    INTELLIGENCE: 'intelligence',
    SOURCE_OPERATIONS: 'source-operations',
    MARKET_INTELLIGENCE: 'market-intelligence',
});

const listeners = new Map();

export function subscribeResource(resource, listener) {
    const resourceListeners = listeners.get(resource) || new Set();
    resourceListeners.add(listener);
    listeners.set(resource, resourceListeners);
    return () => {
        resourceListeners.delete(listener);
        if (resourceListeners.size === 0) listeners.delete(resource);
    };
}

export function invalidateResources(resources) {
    for (const resource of new Set(resources || [])) {
        for (const listener of listeners.get(resource) || []) listener(resource);
    }
}
