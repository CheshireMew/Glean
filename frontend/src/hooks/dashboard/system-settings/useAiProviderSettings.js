import { getAiProviderConfig, setAiProviderConfig } from '../../../api/config';
import { testAiConnection } from '../../../api/pipeline';
import { useRemoteSettings } from '../../useRemoteSettings';

const EMPTY_PROVIDER = { name: 'primary', api_key: '', base_url: '', model: '', input_price_per_million: 0, output_price_per_million: 0 };
const EMPTY_CONFIG = {
    providers: [EMPTY_PROVIDER],
    analysis_concurrency: null,
    enrichment_concurrency: null,
    throttle_seconds: null,
};

const normalizeAiConfig = (response) => ({
    ...response.data,
    providers: response.data?.providers?.length ? response.data.providers : [{ ...EMPTY_PROVIDER }],
});
const isAiConfig = (config) => Array.isArray(config?.providers);

export function useAiProviderSettings() {
    const remote = useRemoteSettings({
        initialValue: EMPTY_CONFIG,
        loadRequest: getAiProviderConfig,
        normalizeResponse: normalizeAiConfig,
        isValid: isAiConfig,
        invalidResponseMessage: '服务器返回的 AI 配置不完整',
        loadErrorMessage: '无法读取当前 AI 配置',
        saveRequest: setAiProviderConfig,
        saveSuccessMessage: 'AI 配置已保存',
        saveErrorMessage: '保存失败',
        saveBlockedMessage: '尚未读取到服务器当前配置，不能保存',
        testRequest: testAiConnection,
        testSuccessMessage: '连接测试成功',
        testErrorMessage: '连接测试失败',
        testBlockedMessage: '尚未读取到服务器当前配置，不能测试连接',
        scopeId: 'ai-provider',
    });

    const updateProvider = (index, field, value) => {
        remote.setValue((previous) => ({
            ...previous,
            providers: previous.providers.map((provider, providerIndex) => (
                providerIndex === index ? { ...provider, [field]: value } : provider
            )),
        }));
    };

    const addProvider = () => {
        remote.setValue((previous) => ({
            ...previous,
            providers: [
                ...previous.providers,
                { ...EMPTY_PROVIDER, name: `fallback-${previous.providers.length}` },
            ],
        }));
    };

    const removeProvider = (index) => {
        remote.setValue((previous) => ({
            ...previous,
            providers: previous.providers.filter((_, providerIndex) => providerIndex !== index),
        }));
    };

    return {
        config: remote.value,
        setConfig: remote.setValue,
        loadState: remote.loadState,
        action: remote.action,
        dirty: remote.dirty,
        reload: remote.reload,
        reset: remote.reset,
        save: remote.save,
        test: remote.test,
        updateProvider,
        addProvider,
        removeProvider,
    };
}
