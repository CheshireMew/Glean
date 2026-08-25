import { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';

import { getEditorialProfiles, saveEditorialProfile } from '../../../api/config';
import { getRequestErrorMessage } from '../listStateHelpers';
import { useUnsavedChangesScope } from '../useUnsavedChanges';

const profileSnapshot = (profile) => JSON.stringify(profile);
const profileIsDirty = (profile, baselineProfiles) => {
    const baseline = baselineProfiles.find((item) => item.slug === profile.slug);
    return !baseline || profileSnapshot(profile) !== profileSnapshot(baseline);
};

export function useEditorialProfiles() {
    const [profiles, setProfiles] = useState([]);
    const [baselineProfiles, setBaselineProfiles] = useState([]);
    const [savingSlug, setSavingSlug] = useState(null);
    const [loadState, setLoadState] = useState({ loading: true, loaded: false, error: null });

    const load = async () => {
        setLoadState({ loading: true, loaded: false, error: null });
        try {
            const response = await getEditorialProfiles();
            if (!Array.isArray(response.data?.profiles)) {
                throw new Error('服务器返回的内容档案不完整');
            }
            setProfiles(response.data.profiles);
            setBaselineProfiles(response.data.profiles);
            setLoadState({ loading: false, loaded: true, error: null });
        } catch (error) {
            setLoadState({ loading: false, loaded: false, error: getRequestErrorMessage(error, '内容档案加载失败') });
        }
    };

    useEffect(() => {
        const timer = window.setTimeout(() => { void load(); }, 0);
        return () => window.clearTimeout(timer);
    }, []);

    const update = (slug, field, value) => {
        setProfiles((previous) => previous.map((profile) => profile.slug === slug ? { ...profile, [field]: value } : profile));
    };

    const add = () => {
        if (!loadState.loaded) return;
        const suffix = profiles.length + 1;
        setProfiles((previous) => [...previous, {
            slug: `new-profile-${suffix}`,
            name: `新内容栏目 ${suffix}`,
            content_type: 'news',
            review_prompt: '',
            enrichment_prompt: '',
            min_score: 5,
            max_items: 12,
            max_per_category: 4,
            max_per_source: 4,
            enabled: false,
            is_default: false,
        }]);
    };

    const isProfileDirty = (profile) => {
        return profileIsDirty(profile, baselineProfiles);
    };

    const dirty = useMemo(
        () => loadState.loaded && profiles.some((profile) => profileIsDirty(profile, baselineProfiles)),
        [baselineProfiles, loadState.loaded, profiles],
    );
    useUnsavedChangesScope('editorial-profiles', dirty);

    const resetProfile = (slug) => {
        const baseline = baselineProfiles.find((item) => item.slug === slug);
        setProfiles((previous) => baseline
            ? previous.map((profile) => profile.slug === slug ? baseline : profile)
            : previous.filter((profile) => profile.slug !== slug));
    };

    const save = async (profile) => {
        if (!loadState.loaded) {
            message.error('尚未读取到服务器当前内容档案，不能保存');
            return;
        }
        setSavingSlug(profile.slug);
        try {
            const response = await saveEditorialProfile(profile);
            const savedProfile = response.data || profile;
            setProfiles((previous) => previous.map((item) => item.slug === profile.slug ? savedProfile : item));
            setBaselineProfiles((previous) => {
                const hasProfile = previous.some((item) => item.slug === savedProfile.slug);
                if (!hasProfile) return [...previous, savedProfile];
                return previous.map((item) => item.slug === savedProfile.slug ? savedProfile : item);
            });
            message.success(`${profile.name} 已保存`);
        } catch (error) {
            message.error(getRequestErrorMessage(error, '内容档案保存失败'));
        } finally {
            setSavingSlug(null);
        }
    };

    return {
        profiles,
        savingSlug,
        loadState,
        dirty,
        isProfileDirty,
        update,
        add,
        resetProfile,
        reload: load,
        save,
    };
}
