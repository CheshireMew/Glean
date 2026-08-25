const TOKEN_KEY = 'token';
const listeners = new Set();
let storageListenerBound = false;

function notifyListeners() {
    listeners.forEach((listener) => listener());
}

function bindStorageListener() {
    if (storageListenerBound || typeof window === 'undefined') {
        return;
    }
    window.addEventListener('storage', (event) => {
        if (event.key === TOKEN_KEY) {
            notifyListeners();
        }
    });
    storageListenerBound = true;
}

export function subscribeAuthSession(listener) {
    bindStorageListener();
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

export function getAuthToken() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return null;
    try {
        const encodedPayload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const paddedPayload = encodedPayload.padEnd(Math.ceil(encodedPayload.length / 4) * 4, '=');
        const payload = JSON.parse(atob(paddedPayload));
        if (!payload.exp || payload.exp * 1000 <= Date.now()) {
            localStorage.removeItem(TOKEN_KEY);
            return null;
        }
        return token;
    } catch {
        localStorage.removeItem(TOKEN_KEY);
        return null;
    }
}

export function setAuthToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
    notifyListeners();
}

export function clearAuthToken() {
    localStorage.removeItem(TOKEN_KEY);
    notifyListeners();
}

export function hasAuthToken() {
    return Boolean(getAuthToken());
}
