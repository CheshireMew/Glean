import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { CaretDown, Lightning, LinkSimple, MagnifyingGlass, Moon, Sun } from '@phosphor-icons/react';
import { FaHome, FaTelegramPlane, FaTwitter, FaBlog, FaGithub, FaBook } from 'react-icons/fa';
import { SiBinance } from 'react-icons/si';

const OKXLogo = ({ className }) => (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" width="1em" height="1em">
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="13" y="3" width="7" height="7" rx="1.5" />
        <rect x="8" y="8" width="7" height="7" rx="1.5" />
        <rect x="3" y="13" width="7" height="7" rx="1.5" />
        <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </svg>
);

const RELATED_LINKS = [
    { key: 'home', label: '主页', icon: FaHome, iconClass: 'text-blue-500' },
    { key: 'telegram', label: 'Telegram 群', icon: FaTelegramPlane, iconClass: 'text-blue-400' },
    { key: 'x', label: 'X (Twitter)', icon: FaTwitter, iconClass: 'text-sky-500' },
    { key: 'blog', label: '博客', icon: FaBlog, iconClass: 'text-purple-500' },
    { key: 'github', label: 'GitHub', icon: FaGithub, iconClass: 'text-gray-800 dark:text-gray-200' },
    { key: 'binance', label: '注册币安', icon: SiBinance, iconClass: 'text-yellow-500' },
    { key: 'okx', label: '注册 OKX', icon: OKXLogo, iconClass: 'text-gray-800 dark:text-gray-200' },
    { key: 'tutorial', label: '币圈教程', icon: FaBook, iconClass: 'text-green-600' },
];

export default function NewsFeedHeader({ searchQuery, onSearchChange, menuOpen, onToggleMenu, darkMode, onToggleDarkMode, links = {} }) {
    const menuButtonRef = useRef(null);
    const menuRef = useRef(null);
    const configuredLinks = RELATED_LINKS.filter((item) => links[item.key]);
    const hasRelatedLinks = configuredLinks.length > 0;

    useEffect(() => {
        if (menuOpen) {
            menuRef.current?.querySelector('[role="menuitem"]')?.focus();
        }
    }, [menuOpen]);

    const handleMenuKeyDown = (event) => {
        const items = Array.from(menuRef.current?.querySelectorAll('[role="menuitem"]') || []);
        const currentIndex = items.indexOf(document.activeElement);
        if (event.key === 'Escape') {
            event.preventDefault();
            onToggleMenu();
            window.requestAnimationFrame(() => menuButtonRef.current?.focus());
            return;
        }
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || items.length === 0) {
            return;
        }
        event.preventDefault();
        let nextIndex;
        if (event.key === 'Home') nextIndex = 0;
        else if (event.key === 'End') nextIndex = items.length - 1;
        else if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1 + items.length) % items.length;
        else nextIndex = (currentIndex - 1 + items.length) % items.length;
        items[nextIndex].focus();
    };

    return (
        <header className="bg-white border-b border-gray-100 sticky top-0 z-40 bg-opacity-90 backdrop-blur-sm dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
            <div className="max-w-7xl mx-auto px-4 min-h-16 py-3 md:py-0 flex flex-wrap md:flex-nowrap items-center justify-between gap-y-3">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white">
                        <Lightning weight="fill" size={18} />
                    </div>
                    <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                        Glean
                    </h1>
                </div>

                <div className="flex order-3 md:order-none w-full md:flex-1 md:max-w-xl md:mx-8 relative">
                    <input
                        type="search"
                        aria-label="搜索公开内容"
                        aria-describedby="public-search-hint"
                        placeholder="搜索公开内容..."
                        value={searchQuery}
                        onChange={(e) => onSearchChange(e.target.value)}
                        className="w-full h-10 bg-gray-50 border-none rounded-full px-10 text-sm focus:ring-1 focus:ring-blue-500 transition-all dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
                    />
                    <span id="public-search-hint" className="sr-only">输入任意关键词后搜索文章、快讯和日报标题</span>
                    <MagnifyingGlass className="absolute left-3.5 top-2.5 text-gray-400" size={18} />
                </div>

                <div className="flex items-center gap-2 md:gap-4">
                    {hasRelatedLinks && <div className="relative menu-dropdown">
                        <button
                            ref={menuButtonRef}
                            type="button"
                            onClick={onToggleMenu}
                            onKeyDown={(event) => {
                                if (!menuOpen && event.key === 'ArrowDown') {
                                    event.preventDefault();
                                    onToggleMenu();
                                } else if (menuOpen && event.key === 'Escape') {
                                    handleMenuKeyDown(event);
                                }
                            }}
                            aria-expanded={menuOpen}
                            aria-haspopup="menu"
                            aria-controls="related-links-menu"
                            aria-label="打开相关链接"
                            className="min-w-10 min-h-10 px-2 md:px-4 py-2 text-sm font-medium text-gray-600 hover:text-blue-600 transition-colors dark:text-gray-300 dark:hover:text-blue-400 flex items-center justify-center gap-1"
                        >
                            <LinkSimple size={17} aria-hidden="true" />
                            <span className="hidden sm:inline">链接</span>
                            <CaretDown size={14} className={`transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
                        </button>
                        <div ref={menuRef} id="related-links-menu" role="menu" aria-hidden={!menuOpen} onKeyDown={handleMenuKeyDown} className={`absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-100 transition-all duration-200 dark:bg-gray-800 dark:border-gray-700 ${menuOpen ? 'opacity-100 visible' : 'opacity-0 invisible'}`}>
                            <div className="py-2">
                                {configuredLinks.map((item) => {
                                    const Icon = item.icon;
                                    return (
                                        <a key={item.key} role="menuitem" tabIndex={menuOpen ? 0 : -1} href={links[item.key]} target="_blank" rel="noopener noreferrer" className="min-h-10 flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-blue-600 transition-colors dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-blue-400">
                                            <span className="flex items-center gap-2"><Icon className={item.iconClass} />{item.label}</span>
                                        </a>
                                    );
                                })}
                            </div>
                        </div>
                    </div>}

                    <button
                        type="button"
                        onClick={onToggleDarkMode}
                        aria-label={darkMode ? '切换到亮色模式' : '切换到暗色模式'}
                        className="min-w-10 min-h-10 p-2 text-gray-400 hover:text-gray-600 transition-colors dark:text-gray-400 dark:hover:text-gray-200 flex items-center justify-center"
                        title={darkMode ? '切换到亮色模式' : '切换到暗色模式'}
                    >
                        {darkMode ? <Sun size={20} /> : <Moon size={20} />}
                    </button>
                </div>
            </div>
        </header>
    );
}

NewsFeedHeader.propTypes = {
    searchQuery: PropTypes.string.isRequired,
    onSearchChange: PropTypes.func.isRequired,
    menuOpen: PropTypes.bool.isRequired,
    onToggleMenu: PropTypes.func.isRequired,
    darkMode: PropTypes.bool.isRequired,
    onToggleDarkMode: PropTypes.func.isRequired,
    links: PropTypes.objectOf(PropTypes.string),
};
