"""Text preparation for posts outside the pilot sample. Copied from scripts/pilot/build_sample.py
(clean + snippet) so that gold tasks and regression cases look exactly like what the AI labellers saw:
title + up to 700 characters around the first keyword, author names, handles, URLs and emails masked."""
import html
import re

KW_HN = r'seilbahn|gondel|kabinenbahn|ropeway|cable car|cablecar|seilschwebebahn|schwebebahn|stadtseilbahn'


def clean(s, authors):
    s = html.unescape(s or '')
    s = re.sub(r'<br\s*/?>', ' ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'https?://\s?\S+|www\.\S+|[\w-]+\.(?:google|com|de|fr|ch|at)/\S+', '[URL]', s)
    s = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[EMAIL]', s)
    s = re.sub(r'@[\w.]+', '[USER]', s)
    for a in (authors if isinstance(authors, (list, tuple)) or hasattr(authors, 'tolist') else []):
        if isinstance(a, str) and len(a.strip()) >= 4:
            s = re.sub(re.escape(a.strip().lstrip('@')), '[USER]', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def snippet(r, kw=KW_HN, n=700):
    title = clean(r['title'] if isinstance(r['title'], str) else '', r['authors'])
    body = clean(r['content'] if isinstance(r['content'], str) else '', r['authors'])
    if len(body) > n:
        m = re.search(kw, body, flags=re.I)
        pos = m.start() if m else 0
        a = max(0, pos - n // 2)
        b = min(len(body), a + n)
        a = max(0, b - n)
        body = ('...' if a > 0 else '') + body[a:b] + ('...' if b < len(body) else '')
    return (title + '\n\n' + body).strip()
