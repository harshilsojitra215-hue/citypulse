"""Official page change monitor.

For each page in projects.yaml (sources.pagewatch.pages): fetch it once per run (robots.txt honoured, one request, our own
user agent), reduce it to normalised main-content text, hash it, compare with the last stored snapshot.
  first time   -> 'baseline': snapshot stored, NO item (a page that merely exists is not news)
  same hash    -> 'unchanged'
  other hash   -> 'changed': new snapshot stored, ONE item of kind 'official_page_change' with a short text diff.
                  Every change is its own record (version_id = new hash), so the pipeline sees each change as an event.
published_at of that item is the time WE detected the change. The real edit time is UNKNOWN unless the page states it.
Stored: normalised text and hash only, no HTML, no images. Test pages may use file:// URLs (see experiments/exp3_pagewatch.py).
"""
import datetime as dt
import difflib
import hashlib
import re
from html.parser import HTMLParser

from ..core import Adapter, HttpError, Item, UTC

SKIP = {'script', 'style', 'noscript', 'nav', 'header', 'footer', 'form', 'svg', 'iframe', 'button', 'select', 'template'}
SKIP_OUTSIDE_MAIN_ONLY = {'header', 'footer'}   # inside <main>, a <header> is usually a section heading (Heilbronn does this)
BLOCK = {'p', 'div', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'tr', 'td', 'th', 'section', 'article',
         'details', 'summary', 'dt', 'dd', 'table', 'blockquote', 'figcaption', 'main', 'aside'}
VOID = {'br', 'img', 'hr', 'meta', 'link', 'input', 'source', 'wbr', 'area', 'base', 'col', 'embed', 'param', 'track'}


class _Text(HTMLParser):
    """Collect text lines. Two passes use the same parser: lines in <main> (if any) and lines in the whole body."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.main = 0
        self._skipped = []          # stack of (tag, counted) for skip tags
        self.lines_all, self.lines_main = [], []
        self.buf_all, self.buf_main = [], []
        self.title = ''
        self._in_title = False

    def _flush(self):
        for buf, dst in ((self.buf_all, self.lines_all), (self.buf_main, self.lines_main)):
            t = re.sub(r'\s+', ' ', ''.join(buf)).strip()
            if t:
                dst.append(t)
            buf.clear()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title':
            self._in_title = True
        if tag in VOID:
            if tag in BLOCK:
                self._flush()
            return
        if tag in SKIP:
            counted = not (tag in SKIP_OUTSIDE_MAIN_ONLY and self.main)
            self._skipped.append((tag, counted))
            self.skip += int(counted)
        if tag == 'main' or a.get('role') == 'main':
            self.main += 1
        if tag in BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag in VOID:
            return
        if tag in SKIP:
            for k in range(len(self._skipped) - 1, -1, -1):
                if self._skipped[k][0] == tag:
                    self.skip -= int(self._skipped.pop(k)[1])
                    break
        if tag == 'main' and self.main:
            self.main -= 1
        if tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.buf_all.append(data)
        if self.main:
            self.buf_main.append(data)


def normalise_html(raw, ignore=()):
    """-> (title, [lines]). Main-content lines if the page has <main>, else the whole body minus nav/header/footer."""
    p = _Text()
    p.feed(raw)
    p._flush()
    lines = p.lines_main if len(' '.join(p.lines_main)) > 400 else p.lines_all
    rx = [re.compile(r, re.I) for r in ignore]
    lines = [ln for ln in lines if not any(r.search(ln) for r in rx)]
    return re.sub(r'\s+', ' ', p.title).strip(), lines


def _word_change(old, new, ctx=6):
    """Show where two similar lines differ: '...words before [old words -> new words] words after...'."""
    a, b = old.split(' '), new.split(' ')
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        pre = ' '.join(a[max(0, i1 - ctx):i1])
        post = ' '.join(a[i2:i2 + ctx])
        parts.append(f"...{pre} [{' '.join(a[i1:i2]) or '(nothing)'} -> {' '.join(b[j1:j2]) or '(nothing)'}] {post}...")
        if len(parts) == 3:
            break
    return ' '.join(parts)


def diff_summary(old_lines, new_lines, max_lines=8, width=170):
    """Line diff. Pure additions and removals are listed (cut at `width`); a line that changed a little is shown as a
    word-level change with a few words of context."""
    cut = lambda s: s if len(s) <= width else s[:width - 1] + '…'  # noqa: E731
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    added, removed, changed = [], [], []
    n_add = n_rem = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        olds, news = old_lines[i1:i2], new_lines[j1:j2]
        n_rem += len(olds)
        n_add += len(news)
        used_new = set()
        for o in olds:
            best = max(range(len(news)), key=lambda k: difflib.SequenceMatcher(None, o, news[k]).ratio(), default=None)
            if best is not None and best not in used_new and difflib.SequenceMatcher(None, o, news[best]).ratio() > 0.6:
                used_new.add(best)
                changed.append(cut(_word_change(o, news[best])))
            else:
                removed.append(cut(o))
        added += [cut(x) for k, x in enumerate(news) if k not in used_new]
    return {'added': n_add, 'removed': n_rem, 'added_lines': added[:max_lines], 'removed_lines': removed[:max_lines],
            'changed_lines': changed[:max_lines]}


class PageWatch(Adapter):
    name = 'pagewatch'
    source_terms = ('Public official page, fetched once per run with robots.txt honoured. We store normalised text and a hash '
                    'for change detection and show a short diff with a link to the original. Copyright stays with the publisher.')

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self.store = None
        self.page_status = {}      # page_id -> [status, detail]
        self.changes = []          # short diffs of pages that changed in this run

    def bind_store(self, store):
        self.store = store

    def fetch(self, project, since):
        out = []
        pages = [p for p in self.cfg.get('pages', []) if p['project'] == project.id]
        errs = []
        for pg in pages:
            pid, url = pg['id'], pg['url']
            now = dt.datetime.now(UTC)
            try:
                body, _ = self.http.get(url, interval=self.interval, robots=not url.startswith('file://'))
                title, lines = normalise_html(body.decode('utf-8', 'replace'), pg.get('ignore', []))
            except HttpError as e:
                self.page_status[pid] = ['error', str(e)[:120]]
                errs.append(pid)
                continue
            if len(' '.join(lines)) < 200:
                self.page_status[pid] = ['error', 'page text under 200 characters: layout changed or page is JavaScript only']
                errs.append(pid)
                continue
            text = '\n'.join(lines)
            h = hashlib.sha1(text.encode()).hexdigest()
            last = self.store.last_snapshot(pid)
            ts = now.isoformat(timespec='seconds')
            if last is None:
                self.store.add_snapshot(pid, url, h, text, ts)
                self.page_status[pid] = ['baseline', f'{len(lines)} lines, hash {h[:10]}']
                continue
            if last[1] == h:
                self.page_status[pid] = ['unchanged', f'hash {h[:10]}, last snapshot {last[0]}']
                continue
            d = diff_summary(last[2].split('\n'), lines)
            self.store.add_snapshot(pid, url, h, text, ts)
            self.page_status[pid] = ['changed', f'+{d["added"]} -{d["removed"]} lines, {last[1][:10]} -> {h[:10]}']
            self.changes.append({'page_id': pid, 'url': url, 'project': project.id, 'previous_snapshot': last[0],
                                 'previous_hash': last[1], 'new_hash': h, 'test': bool(pg.get('test')), **d})
            summ = ' | '.join(['CHANGED: ' + x for x in d['changed_lines'][:5]] + ['ADDED: ' + x for x in d['added_lines'][:5]]
                              + ['REMOVED: ' + x for x in d['removed_lines'][:5]])
            label = pg.get('title') or title
            out.append(Item(self.name, project.id, url, f'Official page changed: {label} (+{d["added"]} / -{d["removed"]} lines)',
                            f'The official page "{label}" changed since {last[0][:10]}. {summ}', now,
                            pg.get('outlet') or re.sub(r'^https?://(www\.)?', '', url).split('/')[0], pg.get('language'),
                            pg.get('country'), 'Other', None, 0, self.source_terms, pid, True,
                            kind='official_page_change', version_id=h))
        if errs and len(errs) == len(pages):
            raise HttpError(-1, 'pages failed: ' + ', '.join(f'{e} ({self.page_status[e][1]})' for e in errs))
        return out
