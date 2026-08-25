import { useCallback, useEffect, useMemo, useState } from 'react';
import { message } from 'antd';

import { getRequestErrorMessage } from './dashboard/listStateHelpers';
import { useUnsavedChangesScope } from './dashboard/useUnsavedChanges';

const responseData = (response) => response.data;
const acceptAny = () => true;
const snapshot = (value) => JSON.stringify(value);

export function useRemoteSettings({
    initialValue,
    loadRequest,
    normalizeResponse = responseData,
    isValid = acceptAny,
    invalidResponseMessage,
    loadErrorMessage,
    saveRequest,
    saveSuccessMessage,
    saveErrorMessage,
    saveBlockedMessage,
    testRequest,
    testSuccessMessage,
    testErrorMessage,
    testBlockedMessage,
    scopeId,
}) {
    const [value, setValue] = useState(initialValue);
    const [baseline, setBaseline] = useState(() => snapshot(initialValue));
    const [loadState, setLoadState] = useState({ loading: true, loaded: false, error: null });
    const [action, setAction] = useState(null);

    const reload = useCallback(async () => {
        setLoadState({ loading: true, loaded: false, error: null });
        try {
            const nextValue = normalizeResponse(await loadRequest());
            if (!isValid(nextValue)) {
                throw new Error(invalidResponseMessage);
            }
            setValue(nextValue);
            setBaseline(snapshot(nextValue));
            setLoadState({ loading: false, loaded: true, error: null });
            return true;
        } catch (error) {
            setLoadState({
                loading: false,
                loaded: false,
                error: getRequestErrorMessage(error, loadErrorMessage),
            });
            return false;
        }
    }, [invalidResponseMessage, isValid, loadErrorMessage, loadRequest, normalizeResponse]);

    useEffect(() => {
        const timer = window.setTimeout(() => { void reload(); }, 0);
        return () => window.clearTimeout(timer);
    }, [reload]);

    const save = useCallback(async () => {
        if (!loadState.loaded) {
            message.error(saveBlockedMessage);
            return false;
        }
        setAction('save');
        try {
            await saveRequest(value);
            setBaseline(snapshot(value));
            message.success(saveSuccessMessage);
            return true;
        } catch (error) {
            message.error(`${saveErrorMessage}: ${getRequestErrorMessage(error, saveErrorMessage)}`);
            return false;
        } finally {
            setAction(null);
        }
    }, [loadState.loaded, saveBlockedMessage, saveErrorMessage, saveRequest, saveSuccessMessage, value]);

    const test = useCallback(async () => {
        if (!testRequest) return false;
        if (!loadState.loaded) {
            message.error(testBlockedMessage);
            return false;
        }
        setAction('test');
        try {
            await testRequest(value);
            message.success(testSuccessMessage);
            return true;
        } catch (error) {
            message.error(`${testErrorMessage}: ${getRequestErrorMessage(error, testErrorMessage)}`);
            return false;
        } finally {
            setAction(null);
        }
    }, [loadState.loaded, testBlockedMessage, testErrorMessage, testRequest, testSuccessMessage, value]);

    const dirty = useMemo(
        () => loadState.loaded && snapshot(value) !== baseline,
        [baseline, loadState.loaded, value],
    );
    const reset = useCallback(() => {
        setValue(JSON.parse(baseline));
    }, [baseline]);

    useUnsavedChangesScope(scopeId, dirty);

    return { value, setValue, loadState, action, dirty, reload, reset, save, test };
}
