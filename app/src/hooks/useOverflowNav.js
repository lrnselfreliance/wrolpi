import {useState, useRef, useLayoutEffect, useCallback} from 'react';

export function useOverflowNav({links, containerRef, homeRef, rightMenuRef, moreRef}) {
    const [visibleCount, setVisibleCount] = useState(links.length);
    const [isReady, setIsReady] = useState(false);
    const itemWidths = useRef([]);
    const itemRefs = useRef([]);
    const moreWidth = useRef(0);

    const itemRefCallback = useCallback((index) => (el) => {
        itemRefs.current[index] = el;
    }, []);

    const recalculate = useCallback(() => {
        const container = containerRef.current;
        if (!container || itemWidths.current.length === 0) return;

        const containerWidth = container.offsetWidth;
        const homeEl = homeRef.current?.firstElementChild || homeRef.current;
        const homeWidth = homeEl ? homeEl.getBoundingClientRect().width : 0;
        const rightWidth = rightMenuRef.current ? rightMenuRef.current.getBoundingClientRect().width : 0;

        const totalAvailable = containerWidth - homeWidth - rightWidth;
        const totalItemsWidth = itemWidths.current.reduce((a, b) => a + b, 0);

        // If all items fit without a More button, show them all.
        if (totalItemsWidth <= totalAvailable) {
            setVisibleCount(itemWidths.current.length);
            return;
        }

        // Otherwise, reserve space for the More button and fit as many as possible.
        const available = totalAvailable - moreWidth.current;
        let count = 0;
        let usedWidth = 0;

        for (let i = 0; i < itemWidths.current.length; i++) {
            const nextWidth = itemWidths.current[i];
            if (usedWidth + nextWidth <= available) {
                usedWidth += nextWidth;
                count++;
            } else {
                break;
            }
        }

        setVisibleCount(count);
    }, [containerRef, homeRef, rightMenuRef]);

    // Measure item widths once after first render.
    useLayoutEffect(() => {
        if (!containerRef.current) return;

        itemWidths.current = itemRefs.current.map(el => {
            if (!el) return 0;
            const child = el.firstElementChild;
            return child ? child.getBoundingClientRect().width : el.getBoundingClientRect().width;
        });

        const moreEl = moreRef.current?.firstElementChild || moreRef.current;
        if (moreEl) {
            moreWidth.current = moreEl.getBoundingClientRect().width;
        }

        recalculate();
        setIsReady(true);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // ResizeObserver for ongoing resizes.
    useLayoutEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const observer = new ResizeObserver(() => {
            recalculate();
        });
        observer.observe(container);
        return () => observer.disconnect();
    }, [containerRef, recalculate]);

    const visibleLinks = links.slice(0, visibleCount);
    const overflowLinks = links.slice(visibleCount);

    return {visibleLinks, overflowLinks, itemRefCallback, isReady};
}
