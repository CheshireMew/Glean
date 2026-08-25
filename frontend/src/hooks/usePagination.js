export const createPaginationConfig = (pagination, onPageChange, defaultPageSize = 10) => ({
    current: pagination.current,
    pageSize: pagination.pageSize || defaultPageSize,
    total: pagination.total,
    showSizeChanger: true,
    showTotal: (total) => `共 ${total} 条`,
    pageSizeOptions: ['10', '20', '50', '100'],
    onChange: (page, pageSize) => {
        if (onPageChange) {
            onPageChange(page, pageSize);
        }
    },
    onShowSizeChange: (_, size) => {
        if (onPageChange) {
            onPageChange(1, size);
        }
    }
});
