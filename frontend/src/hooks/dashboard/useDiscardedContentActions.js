import { deleteReviewEntry } from '../../api/content';
import { clearReviewDecisions, requeueReviewEntry, requeueReviewedContent } from '../../api/pipeline';
import { runListAction } from './listStateHelpers';

export function useDiscardedContentActions(contentKind) {
    const requeueItem = async (id) => {
        await runListAction({
            action: () => requeueReviewEntry(id),
            successMessage: '已恢复到待审核',
            errorMessage: '恢复失败',
        });
    };

    const deleteItem = async (id) => {
        await runListAction({
            action: () => deleteReviewEntry(id),
            successMessage: '删除成功',
            errorMessage: '删除失败',
        });
    };

    const requeueAll = async () => {
        await runListAction({
            action: () => requeueReviewedContent(contentKind),
            successMessage: (res) => `已恢复 ${res.data.restored_count} 条内容`,
            errorMessage: '批量恢复失败',
        });
    };

    const clearAll = async () => {
        await runListAction({
            action: () => clearReviewDecisions(contentKind),
            successMessage: (res) => `已清空 ${res.data.cleared_count} 条审核结果`,
            errorMessage: '清空失败',
        });
    };

    return {
        requeueItem,
        deleteItem,
        requeueAll,
        clearAll,
    };
}
