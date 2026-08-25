import { useCallback, useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { message } from 'antd';

import { exportContent } from '../../api/content';
import { EXPORT_SCOPE } from '../../contracts/content';

const DEFAULT_EXPORT_FIELDS = ['title', 'source_site', 'published_at', 'source_url', 'content'];

export function useDashboardExport(contentKind) {
    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [dates, setDates] = useState([dayjs().subtract(1, 'day'), dayjs()]);
    const [keyword, setKeyword] = useState('');
    const [scope, setScope] = useState(EXPORT_SCOPE.INCOMING);
    const [fields, setFields] = useState(DEFAULT_EXPORT_FIELDS);

    const open = useCallback((nextScope = EXPORT_SCOPE.INCOMING) => {
        setScope(nextScope);
        setDates([dayjs().subtract(1, 'day'), dayjs()]);
        setVisible(true);
    }, []);

    const close = useCallback(() => {
        setVisible(false);
    }, []);

    const submit = useCallback(async () => {
        setLoading(true);
        try {
            const params = { scope, kind: contentKind };
            if (dates?.length === 2) {
                params.start_date = dates[0].toDate().toISOString();
                params.end_date = dates[1].toDate().toISOString();
            }
            if (keyword) {
                params.keyword = keyword;
            }
            if (fields.length > 0) {
                params.fields = fields.join(',');
            }

            const res = await exportContent(params);
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `ainews_export_${scope}_${Date.now()}.json`);
            document.body.appendChild(link);
            link.click();
            link.parentNode.removeChild(link);
            window.URL.revokeObjectURL(url);
            setVisible(false);
            message.success('导出成功');
        } catch (error) {
            console.error(error);
            message.error('导出失败');
        } finally {
            setLoading(false);
        }
    }, [contentKind, dates, fields, keyword, scope]);

    return useMemo(() => ({
        visible,
        loading,
        dates,
        keyword,
        scope,
        fields,
        setDates,
        setKeyword,
        setScope,
        setFields,
        open,
        close,
        submit,
    }), [close, dates, fields, keyword, loading, open, scope, submit, visible]);
}
