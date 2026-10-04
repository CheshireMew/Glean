import { useEffect, useState, useSyncExternalStore } from 'react';

import { getSessionRevision, setBrowserSession, subscribeAuthSession } from './session';
import { getAuthSession, logout } from '../api/auth';

export function useAuthSession() {
    const sessionRevision = useSyncExternalStore(
        subscribeAuthSession,
        getSessionRevision,
        () => 0,
    );
    const [checked, setChecked] = useState(null);
    const [revision, setRevision] = useState(0);
    useEffect(() => {
        let active = true;
        getAuthSession().then(
            () => { if (active) setChecked({ sessionRevision, revision, authenticated: true, error: null }); },
            (error) => { if (active) setChecked({ sessionRevision, revision, authenticated: false,
                error: error.response?.status === 401 ? null : error.message }); },
        );
        return () => { active = false; };
    }, [sessionRevision, revision]);

    return {
        authenticated: Boolean(checked?.sessionRevision === sessionRevision && checked?.revision === revision && checked.authenticated),
        loading: checked?.sessionRevision !== sessionRevision || checked?.revision !== revision,
        error: checked?.sessionRevision === sessionRevision && checked?.revision === revision ? checked.error : null,
        retry: () => { setChecked(null); setRevision((value) => value + 1); },
        login: setBrowserSession,
        logout,
    };
}
