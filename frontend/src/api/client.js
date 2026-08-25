/**
 * API客户端 - 统一处理API请求和响应
 */

import axios from 'axios';
import { API_BASE_URL } from '../config';
import { clearAuthToken, getAuthToken } from '../auth/session';

const client = axios.create({
    baseURL: `${API_BASE_URL}/api`,
    timeout: 30000,
});

client.interceptors.request.use((config) => {
    const token = getAuthToken();
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

client.interceptors.response.use(
    (response) => {
        const data = response.data;
        if (data && typeof data.success !== 'undefined') {
            if (data.pagination) {
                return {
                    ...response,
                    data: {
                        data: data.data,
                        total: data.pagination.total,
                        page: data.pagination.page,
                        limit: data.pagination.limit,
                        pages: data.pagination.pages,
                    },
                };
            }
            return {
                ...response,
                data: Object.prototype.hasOwnProperty.call(data, 'data') ? data.data : data,
            };
        }
        return response;
    },
    (error) => {
        if (error.response) {
            if (error.response.status === 401) {
                clearAuthToken();
                if (!window.location.pathname.includes('/login')) {
                    window.location.href = '/login';
                }
            }

            if (error.response.data && error.response.data.success === false) {
                const customError = new Error(error.response.data.message || '请求失败');
                customError.response = error.response;
                customError.errorType = error.response.data.error?.type;
                customError.errorDetails = error.response.data.error?.details;
                throw customError;
            }
        }
        throw error;
    }
);

export default client;
