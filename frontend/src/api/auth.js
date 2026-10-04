import { requestOperation } from './operations';
import { clearAuthToken, setBrowserSession, setCsrfToken } from '../auth/session';

export const login = async (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await requestOperation('login', { data: formData, headers: { 'X-Glean-Session': 'browser' } });
    const auth = res.data;
    setBrowserSession(auth.csrf_token);
    return auth;
};

export const updateCredentials = (data) => requestOperation('updateCredentials', { data });

export const getAuthSession = async () => {
    const response = await requestOperation('authSession');
    setCsrfToken(response.data.csrf_token);
    return response;
};

export const logout = async () => {
    try {
        await requestOperation('logout');
    } catch (error) {
        if (error.response?.status !== 401) throw error;
    }
    clearAuthToken();
};
