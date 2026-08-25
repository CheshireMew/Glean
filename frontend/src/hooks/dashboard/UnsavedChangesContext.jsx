import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';

import { UnsavedChangesContext } from './useUnsavedChanges';

export function UnsavedChangesProvider({ children }) {
    const [dirtyScopes, setDirtyScopes] = useState(() => new Set());
    const allowUnloadRef = useRef(false);

    const setScopeDirty = useCallback((scopeId, dirty) => {
        if (dirty) allowUnloadRef.current = false;
        setDirtyScopes((previous) => {
            const next = new Set(previous);
            if (dirty) next.add(scopeId);
            else next.delete(scopeId);
            if (next.size === previous.size && [...next].every((scope) => previous.has(scope))) {
                return previous;
            }
            return next;
        });
    }, []);

    const discardUnsavedChanges = useCallback(() => {
        allowUnloadRef.current = true;
        setDirtyScopes(new Set());
    }, []);

    const hasUnsavedChanges = dirtyScopes.size > 0;

    useEffect(() => {
        if (!hasUnsavedChanges) return undefined;
        const handleBeforeUnload = (event) => {
            if (allowUnloadRef.current) return;
            event.preventDefault();
            event.returnValue = '';
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [hasUnsavedChanges]);

    const value = useMemo(() => ({
        hasUnsavedChanges,
        setScopeDirty,
        discardUnsavedChanges,
    }), [discardUnsavedChanges, hasUnsavedChanges, setScopeDirty]);

    return (
        <UnsavedChangesContext.Provider value={value}>
            {children}
        </UnsavedChangesContext.Provider>
    );
}

UnsavedChangesProvider.propTypes = {
    children: PropTypes.node.isRequired,
};
