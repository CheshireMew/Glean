import { getTelegramConfig, setTelegramConfig } from '../../../api/config';
import { testTelegramPush } from '../../../api/pipeline';
import { useRemoteSettings } from '../../useRemoteSettings';

const EMPTY_CONFIG = { bot_token: '', chat_id: '', enabled: false };
const isTelegramConfig = (config) => Boolean(
    config
    && Object.hasOwn(config, 'bot_token')
    && Object.hasOwn(config, 'chat_id')
    && Object.hasOwn(config, 'enabled')
);

export function useTelegramSettings() {
    const remote = useRemoteSettings({
        initialValue: EMPTY_CONFIG,
        loadRequest: getTelegramConfig,
        isValid: isTelegramConfig,
        invalidResponseMessage: '服务器返回的 Telegram 配置不完整',
        loadErrorMessage: '无法读取当前 Telegram 配置',
        saveRequest: setTelegramConfig,
        saveSuccessMessage: 'Telegram 配置已保存',
        saveErrorMessage: '保存失败',
        saveBlockedMessage: '尚未读取到服务器当前配置，不能保存',
        testRequest: testTelegramPush,
        testSuccessMessage: '测试消息发送成功，请检查 Telegram',
        testErrorMessage: '测试发送失败',
        testBlockedMessage: '尚未读取到服务器当前配置，不能发送测试消息',
        scopeId: 'telegram',
    });

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
    };
}
