import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ArticleList from './ArticleList';
import NewsTimeline from './NewsTimeline';

const items = Array.from({ length: 1000 }, (_, index) => ({
  id: index + 1,
  title: `Item ${index + 1}`,
  source_url: `https://example.test/${index + 1}`,
  source_site: 'example',
  published_at: '2026-08-24 10:00:00',
  review_summary: 'Summary',
  source_count: 1,
}));

describe('large public lists', () => {
  it('bounds the rendered article rows while preserving the full logical height', () => {
    const { container } = render(
      <ArticleList items={items} loadingMore={false} hasMore searchQuery="" />,
    );

    const list = container.querySelector('[data-virtualized="true"]');
    expect(list).not.toBeNull();
    expect(list.getAttribute('aria-label')).toBe('文章列表');
    expect(container.querySelectorAll('[role="listitem"]').length).toBeLessThan(40);
    expect(Number.parseFloat(list.style.height)).toBeGreaterThan(100000);
  });

  it('bounds the rendered news rows while keeping all items in the accessibility count', () => {
    const { container } = render(
      <NewsTimeline items={items} loadingMore={false} hasMore searchQuery="" compact />,
    );

    const list = container.querySelector('[data-virtualized="true"]');
    expect(list).not.toBeNull();
    const rows = container.querySelectorAll('[role="listitem"]');
    expect(rows.length).toBeLessThan(40);
    expect(rows[0].getAttribute('aria-setsize')).toBe('1000');
  });
});
