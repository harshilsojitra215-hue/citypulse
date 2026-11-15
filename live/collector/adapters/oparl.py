"""OParl 1.x council information systems (open JSON standard).
Heilbronn: SOMACOS Session on komm.one, licence dl-de/zero-2-0.
Bonn: the official endpoint sits behind a proof-of-work gate; we do not solve it. We request it once per run and report 'gated'.
Items are Papers (Vorlagen): title, reference number, date. Institutional voice, useful as events for the timeline."""
import datetime as dt
from ..core import Adapter, HttpError, Item, UTC


class OParl(Adapter):
    name = 'oparl'
    source_terms = 'OParl open data of the city council information system (Heilbronn: dl-de/zero-2.0). Title, reference, date.'

    def __init__(self, cfg, http):
        super().__init__(cfg, http)
        self._cache = {}
        self.endpoint_status = {}

    def _papers(self, ep, since):
        if ep['id'] in self._cache:
            return self._cache[ep['id']]
        papers = []
        try:
            system = self.http.json(ep['system'], interval=self.interval, robots=False)
            bodies = self.http.json(system['body'], interval=self.interval, robots=False)
            for b in bodies.get('data', []):
                url = b['paper']
                params = {'modified_since': since.strftime('%Y-%m-%dT%H:%M:%S+00:00')}
                for _ in range(self.cfg.get('max_pages', 80)):
                    page = self.http.json(url, interval=self.interval, robots=False, params=params)
                    papers += page.get('data', [])
                    url = (page.get('links') or {}).get('next')
                    params = None
                    if not url:
                        break
            self.endpoint_status[ep['id']] = ('ok', len(papers))
        except HttpError as e:
            self.endpoint_status[ep['id']] = ('gated' if 'gated' in str(e) else 'error', str(e)[:120])
            papers = None
        self._cache[ep['id']] = papers
        return papers

    def fetch(self, project, since):
        out = []
        for ep in self.cfg.get('endpoints', []):
            if ep['project_city'].lower() != project.city.lower() or not project.oparl_terms:
                continue
            papers = self._papers(ep, since)
            if papers is None:
                st = self.endpoint_status[ep['id']]
                raise HttpError(403 if st[0] == 'gated' else -1, f'{ep["id"]}: {st[0]} {st[1]}')
            for p in papers:
                name = (p.get('name') or '').strip()
                if not name or not project.matches_terms(name, project.oparl_terms):
                    continue
                d = p.get('date') or p.get('created') or p.get('modified')
                try:
                    pub = dt.datetime.fromisoformat(d.replace('Z', '+00:00'))
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=dt.timezone(dt.timedelta(hours=1)))
                    pub = pub.astimezone(UTC)
                except Exception:
                    continue
                title = f'{name} ({p.get("reference")})' if p.get('reference') else name
                mod = None
                try:
                    mod = dt.datetime.fromisoformat(p['modified'].replace('Z', '+00:00')).astimezone(UTC)
                except Exception:
                    pass
                out.append(Item(self.name, project.id, p['id'], title, title, pub, ep['id'] + '.ratsinfo', 'de', 'DE',
                                'Other', None, 0, self.source_terms, 'papers?modified_since', kind='council_paper', modified_at=mod))
        return out
