import { deleteReviewEntry, listReviewedContent } from '../../api/content';
import { REVIEW_DECISION } from '../../contracts/content';
import { runListAction } from './listStateHelpers';
import { usePaginatedContentList } from './usePaginatedContentList';

export function useSelectedContentTab(contentKind) {
    const listState = usePaginatedContentList({
        contentKind,
        loadPage: (params) => listReviewedContent({ decision: REVIEW_DECISION.SELECTED, ...params }),
        errorMessage: '加载已选入内容失败',
    });

    const deleteItem = async (id) => {
        await runListAction({
            action: () => deleteReviewEntry(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    return {
        ...listState,
        deleteItem,
    };
}
