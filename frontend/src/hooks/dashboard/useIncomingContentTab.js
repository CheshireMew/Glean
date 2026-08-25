import { deleteSourceContent, listIncomingContent } from '../../api/content';
import { runListAction } from './listStateHelpers';
import { usePaginatedContentList } from './usePaginatedContentList';

export function useIncomingContentTab(contentKind) {
    const listState = usePaginatedContentList({
        contentKind,
        loadPage: listIncomingContent,
        initialPageSize: 20,
        errorMessage: '加载采集池失败',
    });

    const deleteItem = async (id) => {
        await runListAction({
            action: () => deleteSourceContent(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    return {
        ...listState,
        deleteItem,
    };
}
