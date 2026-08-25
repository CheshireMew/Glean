import { deleteArchiveContent, listArchiveContent, restoreArchiveEntry } from '../../api/content';
import { runListAction } from './listStateHelpers';
import { usePaginatedContentList } from './usePaginatedContentList';

export function useArchiveContentTab(contentKind) {
    const listState = usePaginatedContentList({
        contentKind,
        loadPage: listArchiveContent,
        errorMessage: '加载归档池失败',
    });

    const restoreItem = async (id) => {
        await runListAction({
            action: () => restoreArchiveEntry(id),
            successMessage: '已恢复到采集池',
            errorMessage: '恢复失败',
        });
    };

    const deleteItem = async (id) => {
        await runListAction({
            action: () => deleteArchiveContent(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    return {
        ...listState,
        restoreItem,
        deleteItem,
    };
}
