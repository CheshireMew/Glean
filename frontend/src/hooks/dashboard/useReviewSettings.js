import { useCallback } from 'react';

import { getReviewSettings, setReviewSettings } from '../../api/config';
import { useRemoteSettings } from '../useRemoteSettings';

const INITIAL_REVIEW_SETTINGS = { prompt: '', hours: null };
const responseData = (response) => response.data;
const isCompleteReviewSettings = (value) => (
    value
    && Object.hasOwn(value, 'prompt')
    && Object.hasOwn(value, 'hours')
);

export function useReviewSettings(contentKind) {
    const loadRequest = useCallback(() => getReviewSettings(contentKind), [contentKind]);
    const saveRequest = useCallback(
        (value) => setReviewSettings({ hours: value.hours }, contentKind),
        [contentKind],
    );
    const remote = useRemoteSettings({
        initialValue: INITIAL_REVIEW_SETTINGS,
        loadRequest,
        normalizeResponse: responseData,
        isValid: isCompleteReviewSettings,
        invalidResponseMessage: '服务器返回的审核配置不完整',
        loadErrorMessage: '审核配置加载失败',
        saveRequest,
        saveSuccessMessage: '配置已保存',
        saveErrorMessage: '保存配置失败',
        saveBlockedMessage: '尚未读取到服务器当前审核配置，不能保存',
    });

    return {
        reviewPrompt: remote.value.prompt,
        reviewHours: remote.value.hours,
        loadState: remote.loadState,
        setReviewHours: (hours) => remote.setValue((current) => ({ ...current, hours })),
        reload: remote.reload,
        saveSettings: remote.save,
    };
}
