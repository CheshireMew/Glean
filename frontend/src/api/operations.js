import client from './client';
import operations from './operations.json';
import { invalidateResources } from './resources';

function resolvePath(template, pathValues = {}) {
    return template.replace(/\{([^}]+)\}/g, (_, key) => {
        if (!Object.hasOwn(pathValues, key)) throw new Error(`API operation is missing path value: ${key}`);
        return encodeURIComponent(pathValues[key]);
    });
}

export async function requestOperation(operationId, { path, data, ...config } = {}) {
    const operation = operations[operationId];
    if (!operation) throw new Error(`Unknown API operation: ${operationId}`);
    const response = await client.request({
        ...config,
        method: operation.method,
        url: resolvePath(operation.path, path),
        data,
    });
    invalidateResources(operation.invalidates);
    return response;
}

export { operations };
