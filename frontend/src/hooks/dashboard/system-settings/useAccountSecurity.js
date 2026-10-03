import { useState } from 'react';
import { message } from 'antd';

import { updateCredentials } from '../../../api/auth';
import { clearAuthToken } from '../../../auth/session';
import { getRequestErrorMessage } from '../listStateHelpers';

export function useAccountSecurity(form) {
    const [loading, setLoading] = useState(false);

    const submit = async (values) => {
        try {
            setLoading(true);
            await updateCredentials({
                current_password: values.current_password,
                new_username: values.new_username?.trim() || undefined,
                new_password: values.new_password || undefined,
            });
            message.success('账户信息更新成功，请重新登录');
            form.resetFields();
            clearAuthToken();
            window.location.href = '/login';
        } catch (error) {
            message.error(`更新失败: ${getRequestErrorMessage(error, '更新失败')}`);
        } finally {
            setLoading(false);
        }
    };

    return { loading, submit };
}
