import React from 'react';

const TEXT_TAGS = new Set(['b', 'strong', 'i', 'em', 'u', 's', 'code', 'pre', 'br', 'p', 'blockquote', 'ul', 'ol', 'li']);
const OMIT_TAGS = new Set(['script', 'style', 'svg', 'math', 'iframe', 'object', 'embed', 'form', 'input', 'link', 'meta', 'base']);

function renderNode(node, key) {
    if (node.nodeType === 3) return node.textContent;
    if (node.nodeType !== 1) return null;
    const tag = node.tagName.toLowerCase();
    if (OMIT_TAGS.has(tag)) return null;
    const children = Array.from(node.childNodes, (child, index) => renderNode(child, `${key}-${index}`));
    if (tag === 'a') {
        try {
            const url = new URL(node.getAttribute('href') || '');
            if (['https:', 'http:'].includes(url.protocol)) {
                return <a key={key} href={url.href} target="_blank" rel="noopener noreferrer">{children}</a>;
            }
        } catch { /* An invalid or unsupported link is displayed as text. */ }
    }
    if (TEXT_TAGS.has(tag)) return React.createElement(tag, { key }, tag === 'br' ? undefined : children);
    return <React.Fragment key={key}>{children}</React.Fragment>;
}

export default function SafeReportPreview({ content }) {
    const document = new DOMParser().parseFromString(content || '', 'text/html');
    return <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.75 }}>
        {Array.from(document.body.childNodes, (node, index) => renderNode(node, String(index)))}
    </div>;
}
