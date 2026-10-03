import { useState } from 'react';

import { login } from '../api/auth';

export function useLoginForm(navigate, returnTo) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const submit = async (values) => {
        setLoading(true);
        setError('');
        try {
            await login(values.username, values.password);
            navigate(returnTo === '/admin?tab=wechat' ? returnTo : '/admin');
        } catch (error) {
            setError(`登录失败：${error?.message || '请检查管理员账号配置'}`);
        } finally {
            setLoading(false);
        }
    };

    return { loading, error, submit };
}
