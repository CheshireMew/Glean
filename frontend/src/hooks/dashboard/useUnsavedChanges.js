import { createContext, useContext, useEffect } from 'react';

export const UnsavedChangesContext = createContext(null);

export function useUnsavedChangesStatus() {
    const context = useContext(UnsavedChangesContext);
    if (!context) {
        throw new Error('useUnsavedChangesStatus 必须在 UnsavedChangesProvider 中使用');
    }
    return context;
}

export function useUnsavedChangesScope(scopeId, dirty) {
    const context = useContext(UnsavedChangesContext);
    const setScopeDirty = context?.setScopeDirty;

    useEffect(() => {
        if (!setScopeDirty || !scopeId) return undefined;
        setScopeDirty(scopeId, dirty);
        return () => setScopeDirty(scopeId, false);
    }, [dirty, scopeId, setScopeDirty]);
}
