import React, { useRef } from 'react';
import PropTypes from 'prop-types';
import { NEWSFEED_TABS } from '../../contracts/content';

export default function NewsFeedTabs({ activeTab, onChange, tabs = NEWSFEED_TABS }) {
    const tabRefs = useRef([]);

    const handleKeyDown = (event, currentIndex) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            return;
        }
        event.preventDefault();
        const visibleIndexes = tabs.map((_, index) => index);
        const position = Math.max(0, visibleIndexes.indexOf(currentIndex));
        let nextPosition;
        if (event.key === 'Home') nextPosition = 0;
        else if (event.key === 'End') nextPosition = visibleIndexes.length - 1;
        else if (event.key === 'ArrowRight') nextPosition = (position + 1) % visibleIndexes.length;
        else nextPosition = (position - 1 + visibleIndexes.length) % visibleIndexes.length;
        const nextIndex = visibleIndexes[nextPosition];
        tabRefs.current[nextIndex]?.focus();
        onChange(tabs[nextIndex].key);
    };

    return (
        <div className="flex items-center px-6 py-4 border-b border-gray-100 sticky top-28 md:top-16 z-30 bg-white rounded-t-xl dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
            <div className="flex gap-1 overflow-x-auto" role="tablist" aria-label="公开内容栏目">
                {tabs.map((tab, index) => (
                    <button
                        key={tab.key}
                        ref={(node) => { tabRefs.current[index] = node; }}
                        id={`feed-tab-${tab.key}`}
                        type="button"
                        onClick={() => onChange(tab.key)}
                        onKeyDown={(event) => handleKeyDown(event, index)}
                        role="tab"
                        aria-selected={activeTab === tab.key}
                        aria-controls={`feed-panel-${tab.key}`}
                        tabIndex={activeTab === tab.key ? 0 : -1}
                        className={`px-3 py-1 text-sm rounded-md font-medium transition-colors whitespace-nowrap ${activeTab === tab.key ? 'bg-slate-800 text-white dark:bg-blue-600' : 'text-gray-500 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'}`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

NewsFeedTabs.propTypes = {
    activeTab: PropTypes.string.isRequired,
    onChange: PropTypes.func.isRequired,
    tabs: PropTypes.arrayOf(PropTypes.shape({ key: PropTypes.string, label: PropTypes.string })),
};
