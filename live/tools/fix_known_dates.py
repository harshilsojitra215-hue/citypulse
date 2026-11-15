"""Hand-checked date corrections for records whose search-service date is wrong. Idempotent; every row names its evidence.

Run: python -I -X utf8 live/tools/fix_known_dates.py [--db live/data/live_radar_v2.db]
Also applied automatically at the end of every collector run (live/run_collect.py), so a new scan cannot bring a wrong date back.
Only for cases where the stored page text itself shows the right date. Never a guess. A date of None means: the cable car text on
the page has no date of its own, so the record becomes "date unknown" (never counted as new).
"""
import argparse
import os
import sqlite3

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FIXES = [
    # TenderMap list page of Stadt Heilbronn tenders: Exa dated the whole page 11 Nov (another tender's date). The cable car
    # technology tender's own card on the stored page says "Veröffentlicht: 20. Sept. 2026".
    ('https://tendermap.de/buyers/Stadt%20Heilbronn', '2026-09-20T00:00:00+0000',
     'item card on the page ("Veröffentlicht: 20. Sept. 2026"), checked 15 Nov', 'Veröffentlicht: 20. Sept. 2026'),
    # News LIST page of the Zukunftsnetzwerk ÖPNV, dated 3 Nov by the search service. Its only cable car text is the teaser
    # "20.05.2025 Startschuss für urbane Seilbahn in Heilbronn" (found by the audit chat, checked 15 Nov).
    ('https://www.zukunftsnetzwerk-oepnv.de/aktuelles/news/mobilitaetswende', '2025-05-20T00:00:00+0000',
     'teaser date of the cable car item on the list page ("20.05.2025 Startschuss für urbane Seilbahn in Heilbronn"), checked 15 Nov',
     '20.05.2025 Startschuss für urbane Seilbahn in Heilbronn'),
    # Static municipality profile page (Klimaschutz-Kommune Heilbronn), dated 8 Nov by the search service: its one cable car
    # sentence has no date of its own; 8 Nov is the page's crawl or update date. -> date unknown.
    ('https://www.klimaschutz-kommune.de/kommune/heilbronn-stadt/', None,
     'static profile page, the cable car sentence carries no date (checked 15 Nov)',
     'erste Stadt in Baden-Württemberg werden, die eine Seilbahn'),
]


def apply(db, log=print):
    """Apply every fix whose evidence text is still on the stored page. Returns the number of records changed."""
    n = 0
    for url, date, why, proof in FIXES:
        for key, text, pub, known in db.execute('SELECT key, text, published_at, date_known FROM items WHERE url = ?', (url,)).fetchall():
            if proof not in (text or ''):
                log(f'skip {url}: evidence text "{proof}" not in the stored page any more')
                continue
            if date is None:
                if known:
                    db.execute('UPDATE items SET date_known = 0, date_source = ? WHERE key = ?', (why, key))
                    n += 1
                    log(f'{url}: date -> unknown ({why})')
            elif (pub or '')[:10] != date[:10]:
                db.execute('UPDATE items SET published_at = ?, date_known = 1, date_source = ? WHERE key = ?', (date, why, key))
                n += 1
                log(f'{url}: published_at -> {date[:10]} ({why})')
    db.commit()
    return n


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=os.path.join(LIVE, 'data', 'live_radar_v2.db'))
    a = ap.parse_args()
    print(f'{apply(sqlite3.connect(a.db))} records changed')
