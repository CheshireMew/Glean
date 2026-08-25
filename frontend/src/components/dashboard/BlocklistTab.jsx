import React from 'react';
import PropTypes from 'prop-types';

import { useBlacklistKeywords } from '../../hooks/dashboard/useBlacklistKeywords';
import { useBlockedContentList } from '../../hooks/dashboard/useBlockedContentList';
import { useBlocklistRunner } from '../../hooks/dashboard/useBlocklistRunner';
import BlockedItemsPanel from './BlockedItemsPanel';
import BlocklistKeywordManager from './BlocklistKeywordManager';
import BlocklistRunnerPanel from './BlocklistRunnerPanel';

const BlocklistTab = ({ onAddToFeatured, active, contentKind }) => {
    const blockedList = useBlockedContentList(contentKind, active);
    const {
        blacklistKeywords,
        newKeyword,
        newMatchType,
        setNewKeyword,
        setNewMatchType,
        addKeyword,
        removeKeyword,
    } = useBlacklistKeywords(contentKind, active);
    const {
        filterTimeRange,
        filtering,
        setFilterTimeRange,
        applyCurrentBlocklist,
        restoreAll,
        restoreItem,
        deleteBlockedItem,
    } = useBlocklistRunner(contentKind);

    return (
        <div style={{ padding: '0 10px' }}>
            <BlocklistRunnerPanel
                filterTimeRange={filterTimeRange}
                filtering={filtering}
                setFilterTimeRange={setFilterTimeRange}
                applyCurrentBlocklist={applyCurrentBlocklist}
                restoreAll={restoreAll}
            />
            <BlocklistKeywordManager
                blacklistKeywords={blacklistKeywords}
                newKeyword={newKeyword}
                newMatchType={newMatchType}
                setNewKeyword={setNewKeyword}
                setNewMatchType={setNewMatchType}
                addKeyword={addKeyword}
                removeKeyword={removeKeyword}
            />
            <BlockedItemsPanel
                onAddToFeatured={onAddToFeatured}
                blockedList={blockedList}
                restoreItem={restoreItem}
                deleteBlockedItem={deleteBlockedItem}
                contentKind={contentKind}
            />
        </div>
    );
};

BlocklistTab.propTypes = {
    onAddToFeatured: PropTypes.func,
    active: PropTypes.bool,
    contentKind: PropTypes.string,
};

export default BlocklistTab;
