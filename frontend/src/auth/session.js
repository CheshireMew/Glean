const listeners = new Set();
let revision = 0;
let csrf = null;
// Clear credentials left by versions that persisted a bearer token in browser storage.
localStorage.removeItem('token');

function notifyListeners() {
    listeners.forEach((listener) => listener());
}

export function subscribeAuthSession(listener) {
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

export const getSessionRevision = () => revision;
export const getCsrfToken = () => csrf;
export const setCsrfToken = (value) => { csrf = value || null; };

export function setBrowserSession(value) {
    setCsrfToken(value);
    revision += 1;
    notifyListeners();
}

export function clearAuthToken() {
    csrf = null;
    localStorage.removeItem('token');
    revision += 1;
    notifyListeners();
}
