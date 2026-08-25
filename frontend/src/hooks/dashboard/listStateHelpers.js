import { message } from 'antd';

export function getRequestErrorMessage(error, fallback = '请求失败') {
    return error?.message || fallback;
}

export async function runListAction({
    action,
    successMessage,
    errorMessage,
}) {
    try {
        const result = await action();
        message.success(typeof successMessage === 'function' ? successMessage(result) : successMessage);
        return result;
    } catch (error) {
        message.error(`${errorMessage}: ${getRequestErrorMessage(error, errorMessage)}`);
        return null;
    }
}
