"""Date recovery rules and the output gate (names before 'shared this', page furniture). Offline, no network.
Run: python -I -X utf8 -m pytest live/tests/test_dates_and_masking.py -q
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collector.core import UTC, Store, mask_for_kind  # noqa: E402
from collector.dates import from_text, from_url, parse_any, recover_dates  # noqa: E402


def d(t):
    return t.strftime('%Y-%m-%d') if t else None


def test_url_dates():
    assert d(from_url('https://www.stimme.de/2026/11/05/seilbahn-heilbronn')) == '2026-11-05'
    assert d(from_url('https://ga.de/bonn/seilbahn-2026-10-30-abc')) == '2026-10-30'
    assert d(from_url('https://x.fr/actu/20261103_cable')) == '2026-11-03'
    assert from_url('https://example.org/article/123456') is None
    assert from_url('https://example.org/2031/01/01/future') is None          # not plausible: in the future
    assert from_url('https://example.org/2026/13/40/x') is None               # not a real date


def test_text_dates():
    assert d(from_text('[2026-10-06 · [USER] shared this] Seilbahn')) == '2026-10-06'
    assert d(from_text('05.11.2026 - Gemeinderat berät')) == '2026-11-05'
    assert d(from_text('5 Nov 2026 - Câble C1')) == '2026-11-05'
    assert d(from_text('12 okt. 2026 Seilbahn')) == '2026-10-12'
    assert from_text('Seilbahn Heilbronn: Gemeinderat am 05.11.2026') is None   # only a LEADING date counts
    assert d(parse_any('2026-11-07T10:45:53+01:00')) == '2026-11-07'


def test_recover_never_touches_known_dates(tmp_path):
    s = Store(str(tmp_path / 'x.db'))
    now = dt.datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S+0000')
    for key, url, known in [('a', 'https://news.example/2026/11/05/seilbahn', 0), ('b', 'https://news.example/no-date', 0),
                            ('c', 'https://news.example/2026/11/01/known', 1)]:
        s.db.execute('INSERT INTO items(key, url, title, text, published_at, kind, date_known) VALUES (?,?,?,?,?,?,?)',
                     (key, url, 'Seilbahn', 'Text', now, 'news', known))
    c = recover_dates(s, http=None, fetch_pages=False, log=lambda *_: None)
    rows = dict(((k, (p[:10], dk, src)) for k, p, dk, src in s.db.execute('SELECT key, published_at, date_known, date_source FROM items')))
    assert rows['a'] == ('2026-11-05', 1, 'url')
    assert rows['b'][1] == 0 and rows['b'][2] is None                         # unknown stays unknown, no guess
    assert rows['c'] == (now[:10], 1, None)                                   # a known date is never changed
    assert c['url'] == 1 and c['still_unknown'] == 1


def test_linkedin_slugs_in_text_are_masked():
    """15 Nov audit: a Bonn item carried '/posts/<firstname-lastname-id>_neuer-sachstand' in its text."""
    s = mask_for_kind('social_link', '[USER] /posts/max-mustermann-1a2b3c_neuer-sachstand-zur-bonner-seilbahn and linkedin.com/in/erika-musterfrau-99')
    assert 'mustermann' not in s and 'musterfrau' not in s
    assert '/posts/[USER]_neuer-sachstand' in s and 'linkedin.com/in/[USER]' in s
    assert mask_for_kind('news', 'Siehe /posts/ und linkedin.com/company/stadt-bonn') == 'Siehe /posts/ und linkedin.com/company/stadt-bonn'


def test_activity_date_in_text_beats_a_crawl_date(tmp_path):
    """15 Nov: LinkedIn profile pages were dated by the search service's crawl (28 Oct) though their text says the activity was
    on 6 Oct; they were counted as new after 27 Oct. The date in the item's own text must win, also over a known date."""
    from collector.dates import fix_activity_dates
    s = Store(str(tmp_path / 'y.db'))
    rows = [('li', 'https://linkedin.com/in/x', '[2026-10-06 · [USER] shared this] Seilbahn-Effekt', '2026-10-28T00:00:00+0000'),
            ('ok', 'https://news.example/a', 'Seilbahn Heilbronn: Gemeinderat', '2026-11-03T00:00:00+0000'),
            ('same', 'https://linkedin.com/in/y', '[2026-11-04 · [USER] liked this] Seilbahn', '2026-11-04T12:00:00+0000'),
            ('dash', 'https://linkedin.com/in/z', '- [2026-10-12 · [USER] shared this] BUGA', '2026-11-04T00:00:00+0000')]
    for key, url, text, pub in rows:
        s.db.execute('INSERT INTO items(key, url, title, text, published_at, kind, date_known) VALUES (?,?,?,?,?,?,1)',
                     (key, url, '', text, pub, 'social_link'))
    assert fix_activity_dates(s, log=lambda *_: None) == 2
    got = dict(s.db.execute('SELECT key, substr(published_at,1,10) FROM items').fetchall())
    assert got == {'li': '2026-10-06', 'ok': '2026-11-03', 'same': '2026-11-04', 'dash': '2026-10-12'}
    assert fix_activity_dates(s, log=lambda *_: None) == 0                     # idempotent


def test_names_before_actions_are_masked():
    assert mask_for_kind('social_link', '[2026-10-06 · Burim Sopaj shared this] Seilbahn') == '[2026-10-06 · [USER] shared this] Seilbahn'
    assert mask_for_kind('web', 'Anna-Lena Müller hat einen Beitrag geteilt') == '[USER] hat einen Beitrag geteilt'
    assert mask_for_kind('social_link', 'Marie Dubois a partagé une publication').startswith('[USER]')
    assert mask_for_kind('social_link', 'Jean-Pierre Martin reposted this · 2w').startswith('[USER] reposted this')


def test_places_and_projects_are_not_masked():
    assert mask_for_kind('news', 'Die Seilbahn in Koblenz hat geteilt: die Meinungen') == 'Die Seilbahn in Koblenz hat geteilt: die Meinungen'
    assert mask_for_kind('news', 'Paris Câble C1 shared this week a new timetable') == 'Paris Câble C1 shared this week a new timetable'
    assert mask_for_kind('social_link', "Stadt Heilbronn's post about the Seilbahn") == "Stadt Heilbronn's post about the Seilbahn"


def test_page_furniture_is_removed():
    out = mask_for_kind('social_link', 'Log in Log in Forgotten account? ## Uhlmann Group []( ### has joined [IPAI](https://ipai.de/x)')
    assert 'Log in' not in out and 'Forgotten' not in out and '#' not in out and '[](' not in out and 'https' not in out
    assert 'Uhlmann Group' in out and 'IPAI' in out


def test_social_page_headers_and_photo_credits_are_masked():
    # real snippets from the 15 Nov export (Facebook and Instagram search results)
    fb = mask_for_kind('social_link', "Forgot Account? Reyad in Germany's Post Reyad in Germany Friday, November 6, 2026 at 10:30 AM · "
                                      "Image 1: Floating above the autumn colors of Koblenz.")
    assert 'Reyad' not in fb and 'Forgot' not in fb and 'Image 1' not in fb and 'Floating above' in fb
    assert 'Burim' not in mask_for_kind('social_link', "Burim Sopaj's post Burim Sopaj Friday 30 October 2026 · Seilbahn")
    ig = mask_for_kind('social_link', 'Follow Kölner Seilbahn Photo by Anastasiia on November 08, 2026. May be an image of cablecar, '
                                      'May be an image of train. Gondel')
    assert 'Anastasiia' not in ig and 'May be an image' not in ig and 'Kölner Seilbahn' in ig and 'Gondel' in ig
    assert 'seilbahn_koblenz' not in mask_for_kind('social_link', "seilbahn_koblenz's profile picture Photo by Seilbahn Koblenz on "
                                                                  "November 05, 2026. Fahrplan")
    assert mask_for_kind('social_link', "Stadt Heilbronn's post about the Seilbahn") == "Stadt Heilbronn's post about the Seilbahn"


def test_foreign_login_menus_and_wikipedia_code_are_removed():
    ga = mask_for_kind('social_link', 'Logáil Isteach Logáil Isteach Dearmad déanta agat ar do chuntas? Rheinseilbahn Köln')
    assert ga == 'Rheinseilbahn Köln'
    nav = mask_for_kind('news', 'Springe zur Navigation Springe zum Inhalt. Menü Schließen Cookie-Einstellungen Seilbahn Koblenz')
    assert nav.strip(' .') == 'Seilbahn Koblenz'
    wiki = mask_for_kind('web', 'Un article de Wikipédia. \'\'Plage Bleue\'\' "},"alt inter1":{"wt":""},"lieu inter2":{"wt":"Valenton"},'
                                ' {{BS-table}} [[Ligne 8 du métro de Paris|Ligne 8]] [https://x.fr/a Le Parisien] Câble C1')
    for bad in ('{"wt"', '{{', '[[', "''", 'https', '"}'):
        assert bad not in wiki, bad
    assert 'Ligne 8' in wiki and 'Le Parisien' in wiki and 'Câble C1' in wiki
    tbl = mask_for_kind('web', '| Ort | Bahn |\n|---|---|\n| Koblenz | Seilbahn |')
    assert '| |' not in tbl and 'Koblenz' in tbl and '---' not in tbl


def test_comment_thread_names_tag_lists_and_bylines_are_masked():
    # real shapes from the 15 Nov export: a Facebook comment thread, a LinkedIn tag list, a news byline
    th = mask_for_kind('social_link', 'Seilbahn Koblenz [...] Danuta Kiluk Miejsce mega 1w 1 View 1 reply Willy van der Linden Heel leuk '
                                      '1w 1 Radoslawa Kurtys Byłam 1w 1 View 1 reply Qadir umuvumbuzi Koblenz 5d [...] Tan Ya Es sollen Bäume '
                                      'gefällt werden 5d 20 Image 6Image 7 View all 2 replies Image 8Top fan Die Seilbahn ist gut')
    for name in ('Danuta', 'Kiluk', 'Willy', 'Linden', 'Radoslawa', 'Qadir', 'Tan Ya', 'View all', 'Top fan', 'Image 6'):
        assert name not in th, name
    assert 'Bäume gefällt werden' in th and 'Die Seilbahn ist gut' in th and 'Heel leuk' in th
    tags = mask_for_kind('social_link', 'of applied AI together. [USER], [USER], Kristin Seyboth, [USER], Timo Gessmann, Grit Sommer, PhD '
                                        'Moritz Gräter, Dr. Benjamin [USER], Carolin Spaeth #IPAI')
    for name in ('Kristin', 'Timo', 'Grit', 'Moritz', 'Benjamin', 'Carolin'):
        assert name not in tags, name
    assert 'applied AI together' in tags and '#IPAI' in tags
    news = mask_for_kind('news', 'Große Pläne für Heilbronn: Stadt will zum Roboter-Hotspot werden von Frank Wittmer Stimme+ Logo')
    assert 'Wittmer' not in news and 'Roboter-Hotspot' in news and 'Stimme+ Logo' not in news
    assert mask_for_kind('news', 'Der Bau von Heilbronn Süd beginnt') == 'Der Bau von Heilbronn Süd beginnt'   # not a byline
    assert mask_for_kind('news', 'Bonn, Köln, Koblenz und Paris') == 'Bonn, Köln, Koblenz und Paris'           # a place list stays
    ui = mask_for_kind('social_link', 'Post Log inSign up Post Bravo à tous. No comments yet. Start the conversation. Never miss a post '
                                      'from datenmassiv for Instagram to stay in the loop. See more')
    assert ui == 'Bravo à tous.'


def test_profile_titles_glued_handles_and_listed_first_names():
    assert mask_for_kind('social_link', 'Elisabeth Messner on Reels - Facebook') == '[USER] - Facebook'
    assert mask_for_kind('social_link', '#autumn #stuttgart #new | Jakob Maier - Facebook') == '#autumn #stuttgart #new | [USER] - Facebook'
    assert mask_for_kind('social_link', 'Rheinseilbahn Köln - Facebook') == 'Rheinseilbahn Köln - Facebook'
    x = mask_for_kind('social_link', '[USER] So Janu@Janu2So Nov 13 Cette photo c’est a gare de Créteil')
    assert 'Janu' not in x and 'Cette photo' in x
    assert mask_for_kind('social_link', 'Burim Sopaj') == '[USER]'
    w = mask_for_kind('web', 'sagt Oberbürgermeisterin Miriam Scherff. Mit Konstantin Gold in Köln')
    assert 'Scherff' not in w and 'Konstantin' not in w and 'Köln' in w


def test_long_names_greetings_and_photo_credits():
    assert 'Maheen' not in mask_for_kind('social_link', "We're proud to share that Abdul Matin Sheikh Maheen, Founder and CEO")
    assert mask_for_kind('video_comment', 'Hallo Adrian! Ja, die deutsche Tonspur kommt') == 'Hallo [USER]! Ja, die deutsche Tonspur kommt'
    assert mask_for_kind('video_comment', 'Hallo Koblenz!') == 'Hallo Koblenz!'
    cr = mask_for_kind('social_link', 'CC BY 4.0: Bundesverfassungsgericht Karlsruhe – Asmodea Oaktree; Das deutsche Eck – Flyerx. [...] Koblenz')
    assert 'Asmodea' not in cr and 'Flyerx' not in cr and 'Bundesverfassungsgericht Karlsruhe' in cr
    assert mask_for_kind('social_link', 'Jesca Discovers - YouTube') == '[USER] - YouTube'
    th = mask_for_kind('social_link', 'Koblenz 5d [...] o Hysenbelliu Koblenca e pipos shume e bukur 1w 2')
    assert 'Hysenbelliu' not in th and 'shume e bukur' in th


def test_institutions_named_after_people_stay():
    assert mask_for_kind('web', 'Die Dieter Schwarz Stiftung fördert den IPAI') == 'Die Dieter Schwarz Stiftung fördert den IPAI'
    assert mask_for_kind('web', 'am Robert-Bosch-Krankenhaus in Stuttgart') == 'am Robert-Bosch-Krankenhaus in Stuttgart'
    assert mask_for_kind('web', 'sagte Dieter Schwarz heute') == 'sagte [USER] heute'


def test_names_next_to_masked_names_and_caption_handles():
    t = mask_for_kind('social_link', 'at the Experience Day in Heilbronn. Timon Höfer and Anna Weber approached it')
    assert 'Timon' not in t and 'Weber' not in t and 'Experience Day' in t
    assert mask_for_kind('social_link', r'xl2\_gmbh 🤖 XL2 Innovation Bites: Das war’s!').startswith('[USER] 🤖 XL2')
    assert mask_for_kind('social_link', 'seit 2020 fährt die Seilbahn') == 'seit 2020 fährt die Seilbahn'
    assert '_hn' not in mask_for_kind('social_link', r'to the @ipai\_hn Experience Day')
    nl = mask_for_kind('web', 'Accepteer analytics-cookies om deze content te kunnen bekijken. Cookie-instellingen imec cleanroom')
    assert nl == 'imec cleanroom'


def test_html_class_residue_and_emails_are_removed():
    t = mask_for_kind('official', 'Zurück img:first-child]:pt-0 data-[size=sm]:gap-4 *:[img:last-child]:rounded-b-xl group/card flex '
                                  'flex-col mb-8"> Stadt Heilbronn Vergabestelle E-Mail vergabemanagement@stadt-heilbronn.de Telefon')
    assert t == 'Zurück Stadt Heilbronn Vergabestelle E-Mail [EMAIL] Telefon'
