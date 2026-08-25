import { useEffect, useState } from 'react';
import { message } from 'antd';

import { createAnalystApiKey, deleteAnalystApiKey, getAnalystApiKeys, setAnalystApiKeyEnabled } from '../../../api/pipeline';
import { getRequestErrorMessage } from '../listStateHelpers';

export function useApiKeys() {
    const [apiKeys, setApiKeys] = useState([]);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [newKeyName, setNewKeyName] = useState('');
    const [newKeyNotes, setNewKeyNotes] = useState('');
    const [createdKey, setCreatedKey] = useState(null);
    const [loadState, setLoadState] = useState({ loading: true, loaded: false, error: null });

    async function loadApiKeys() {
        setLoadState({ loading: true, loaded: false, error: null });
        try {
            const res = await getAnalystApiKeys();
            if (!Array.isArray(res.data)) {
                throw new Error('服务器返回的 API 密钥列表不完整');
            }
            setApiKeys(res.data);
            setLoadState({ loading: false, loaded: true, error: null });
        } catch (error) {
            setLoadState({ loading: false, loaded: false, error: getRequestErrorMessage(error, 'API 密钥列表加载失败') });
        }
    }

    useEffect(() => {
        const timer = setTimeout(() => {
            void loadApiKeys();
        }, 0);
        return () => clearTimeout(timer);
    }, []);

    const resetModal = () => {
        setShowCreateModal(false);
        setNewKeyName('');
        setNewKeyNotes('');
    };

    const createKey = async () => {
        if (!loadState.loaded) {
            message.error('尚未读取到服务器当前密钥列表，不能创建');
            return;
        }
        if (!newKeyName.trim()) {
            message.warning('请输入密钥名称');
            return;
        }
        try {
            const res = await createAnalystApiKey(newKeyName, newKeyNotes);
            message.success(`密钥创建成功: ${res.data.key_name}`);
            setCreatedKey(res.data.api_key);
            resetModal();
            await loadApiKeys();
        } catch (error) {
            message.error(`创建失败: ${getRequestErrorMessage(error, '创建失败')}`);
        }
    };

    const deleteKey = async (keyId, keyName) => {
        if (!loadState.loaded) {
            message.error('尚未读取到服务器当前密钥列表，不能删除');
            return;
        }
        try {
            await deleteAnalystApiKey(keyId);
            message.success(`密钥 "${keyName}" 已删除`);
            await loadApiKeys();
        } catch (error) {
            message.error(`删除失败: ${getRequestErrorMessage(error, '删除失败')}`);
        }
    };

    const copyKey = (apiKey) => {
        navigator.clipboard.writeText(apiKey);
        message.success('密钥已复制到剪贴板');
    };

    const setKeyEnabled = async (keyId, enabled) => {
        if (!loadState.loaded) {
            message.error('尚未读取到服务器当前密钥列表，不能修改');
            return;
        }
        try {
            await setAnalystApiKeyEnabled(keyId, enabled);
            await loadApiKeys();
        } catch (error) {
            message.error(`更新失败: ${getRequestErrorMessage(error, '更新失败')}`);
        }
    };

    return {
        apiKeys,
        loadState,
        showCreateModal,
        newKeyName,
        newKeyNotes,
        setShowCreateModal,
        setNewKeyName,
        setNewKeyNotes,
        resetModal,
        createKey,
        deleteKey,
        copyKey,
        createdKey,
        setCreatedKey,
        setKeyEnabled,
        reload: loadApiKeys,
    };
}
