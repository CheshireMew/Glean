import { useEffect, useState, useSyncExternalStore } from 'react';

import { getAuthToken, setAuthToken, subscribeAuthSession } from './session';
import { getAuthSession, logout } from '../api/auth';

export function useAuthSession() {
    const token = useSyncExternalStore(
        subscribeAuthSession,
        getAuthToken,
        () => null,
    );
    const [checked, setChecked] = useState(null);
    const [revision, setRevision] = useState(0);
    useEffect(() => {
        if (!token) return;
        let active = true;
        getAuthSession().then(
            () => { if (active) setChecked({ token, error: null }); },
            (error) => { if (active) setChecked({ token, error: error.message }); },
        );
        return () => { active = false; };
    }, [token, revision]);

    return {
        token,
        authenticated: Boolean(token && checked?.token === token && !checked.error),
        loading: Boolean(token && checked?.token !== token),
        error: token && checked?.token === token ? checked.error : null,
        retry: () => { setChecked(null); setRevision((value) => value + 1); },
        login: setAuthToken,
        logout,
    };
}
