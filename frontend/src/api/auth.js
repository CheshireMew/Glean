import { requestOperation } from './operations';
import { clearAuthToken, setAuthToken } from '../auth/session';

export const login = async (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await requestOperation('login', { data: formData });
    const auth = res.data;
    if (auth.access_token) {
        setAuthToken(auth.access_token);
    }
    return auth;
};

export const updateCredentials = (data) => requestOperation('updateCredentials', { data });

export const getAuthSession = () => requestOperation('authSession');

export const logout = async () => {
    try {
        await requestOperation('logout');
    } catch (error) {
        if (error.response?.status !== 401) throw error;
    }
    clearAuthToken();
};
