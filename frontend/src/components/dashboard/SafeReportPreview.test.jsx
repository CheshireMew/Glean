import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SafeReportPreview from './SafeReportPreview';

describe('safe report preview', () => {
    it('preserves report formatting and ordinary source links', () => {
        const { container } = render(<SafeReportPreview content={'<b>标题</b>\n<a href="https://example.org/article">原文</a>'} />);
        expect(container.querySelector('b')).toHaveTextContent('标题');
        expect(screen.getByRole('link', { name: '原文' })).toHaveAttribute('href', 'https://example.org/article');
        expect(screen.getByRole('link')).toHaveAttribute('rel', 'noopener noreferrer');
    });
    it('removes executable links, event handlers, and embedded content', () => {
        const { container } = render(<SafeReportPreview content={'<a href="java&#x73;cript:alert(1)" onclick="alert(1)">恶意链接</a><img src=x onerror="alert(1)"><svg onload="alert(1)"></svg><script>alert(1)</script><b onclick="alert(1)">保留正文</b>'} />);
        expect(screen.getByText('恶意链接')).toBeInTheDocument();
        expect(screen.getByText('保留正文')).toBeInTheDocument();
        expect(container.querySelector('a, img, svg, script, [onclick], [onerror]')).toBeNull();
    });
});
