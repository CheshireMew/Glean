import React, { useCallback, useEffect, useRef, useState } from 'react';

const VIRTUALIZE_AFTER = 60;

function findIndexAtOffset(offsets, value) {
    let low = 0;
    let high = Math.max(offsets.length - 2, 0);
    while (low < high) {
        const middle = Math.floor((low + high) / 2);
        if (offsets[middle + 1] <= value) low = middle + 1;
        else high = middle;
    }
    return low;
}

function MeasuredRow({ itemKey, top, index, count, onSize, children, className }) {
    const ref = useRef(null);

    useEffect(() => {
        const node = ref.current;
        if (!node || typeof ResizeObserver === 'undefined') return undefined;
        const measure = () => onSize(itemKey, node.getBoundingClientRect().height);
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(node);
        return () => observer.disconnect();
    }, [itemKey, onSize]);

    return (
        <div
            ref={ref}
            role="listitem"
            aria-posinset={index + 1}
            aria-setsize={count}
            className={className}
            style={{ position: 'absolute', top, left: 0, right: 0 }}
        >
            {children}
        </div>
    );
}

export default function VirtualWindowList({
    items,
    itemKey = (item) => item.id,
    estimateSize,
    overscan = 6,
    renderItem,
    className = '',
    itemClassName = '',
    ariaLabel,
}) {
    const containerRef = useRef(null);
    const measuredSizes = useRef(new Map());
    const [measurementVersion, setMeasurementVersion] = useState(0);
    const [viewport, setViewport] = useState(() => ({
        scrollY: typeof window === 'undefined' ? 0 : window.scrollY,
        height: typeof window === 'undefined' ? 800 : window.innerHeight || 800,
        containerTop: 0,
    }));

    useEffect(() => {
        measuredSizes.current.clear();
        setMeasurementVersion((version) => version + 1);
    }, [items]);

    useEffect(() => {
        if (items.length <= VIRTUALIZE_AFTER) return undefined;
        let frame = null;
        const updateViewport = () => {
            if (frame !== null) return;
            frame = window.requestAnimationFrame(() => {
                frame = null;
                const node = containerRef.current;
                const containerTop = node
                    ? node.getBoundingClientRect().top + window.scrollY
                    : 0;
                setViewport({
                    scrollY: window.scrollY,
                    height: window.innerHeight || 800,
                    containerTop,
                });
            });
        };
        updateViewport();
        window.addEventListener('scroll', updateViewport, { passive: true });
        window.addEventListener('resize', updateViewport);
        return () => {
            window.removeEventListener('scroll', updateViewport);
            window.removeEventListener('resize', updateViewport);
            if (frame !== null) window.cancelAnimationFrame(frame);
        };
    }, [items.length]);

    const onSize = useCallback((key, size) => {
        if (!Number.isFinite(size) || size <= 0 || measuredSizes.current.get(key) === size) return;
        measuredSizes.current.set(key, size);
        setMeasurementVersion((version) => version + 1);
    }, []);

    const layout = (() => {
        void measurementVersion;
        const offsets = [0];
        for (const item of items) {
            offsets.push(offsets[offsets.length - 1] + (measuredSizes.current.get(itemKey(item)) || estimateSize));
        }
        return { offsets, totalSize: offsets[offsets.length - 1] };
    })();

    if (items.length <= VIRTUALIZE_AFTER) {
        return (
            <div role="list" aria-label={ariaLabel} className={className}>
                {items.map((item, index) => (
                    <div
                        key={itemKey(item)}
                        role="listitem"
                        aria-posinset={index + 1}
                        aria-setsize={items.length}
                        className={itemClassName}
                    >
                        {renderItem(item, index)}
                    </div>
                ))}
            </div>
        );
    }

    const relativeStart = Math.max(viewport.scrollY - viewport.containerTop, 0);
    const firstVisible = findIndexAtOffset(layout.offsets, relativeStart);
    const lastVisible = findIndexAtOffset(
        layout.offsets,
        Math.min(relativeStart + viewport.height, layout.totalSize),
    );
    const start = Math.max(firstVisible - overscan, 0);
    const end = Math.min(lastVisible + overscan + 1, items.length);

    return (
        <div
            ref={containerRef}
            role="list"
            aria-label={ariaLabel}
            className={className}
            style={{ position: 'relative', height: layout.totalSize }}
            data-virtualized="true"
        >
            {items.slice(start, end).map((item, sliceIndex) => {
                const index = start + sliceIndex;
                const key = itemKey(item);
                return (
                    <MeasuredRow
                        key={key}
                        itemKey={key}
                        top={layout.offsets[index]}
                        index={index}
                        count={items.length}
                        onSize={onSize}
                        className={itemClassName}
                    >
                        {renderItem(item, index)}
                    </MeasuredRow>
                );
            })}
        </div>
    );
}
