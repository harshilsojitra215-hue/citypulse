"""The four review queues: where their items come from, which fields are hidden while labelling (blind queues),
and which labels a human may give. See docs/REVIEW_API.md."""
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config

RELATIONS = ["same", "related", "opposing", "unrelated"]
STANCES = ["support", "oppose", "neutral", "mixed"]
ABOUT = ["yes", "passing", "no"]
VERDICTS = ["confirmed", "wrong_date", "wrong_content", "source_dead"]
PROJECTS = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "other_urban_cablecar", "ipai", "heilbronn_other",
            "leisure_cablecar", "unrelated"]
TARGET_PROJECT = "heilbronn_cablecar"
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
MAX_NOTE = 2000


class LabelError(ValueError):
    pass


class QueueUnavailable(RuntimeError):
    pass


PAIR_RULES_FALLBACK = """- **same**: both claims express the same argument or the same fact. An analyst would count them together. Wording does not matter.
  - For arguments (reasons for or against): the city does not matter.
  - For factual reports (a decision, a date, a cost figure): it must be the same fact or event. The same kind of event in two cities is "related".
- **opposing**: both address the same specific point but assert opposite things.
- **related**: same sub-issue, but a different point, a different fact, or only partial overlap.
- **unrelated**: different issue.
- Judge the point being made, not the wording. Shared words alone do not make claims the same.
- If unsure between "same" and "related", choose "related".
- Do not use outside knowledge about how the projects turned out."""

STANCE_RULES = """Judge only from the excerpt (open the link if the excerpt is not enough).

**Is it about the Heilbronn cable car?**
- **yes**: the planned urban cable car in Heilbronn is a real subject of the post (also when it is one of several projects discussed).
- **passing**: it is only a side remark (one line in a text about something else).
- **no**: it is about something else (another city's cable car, the IPAI without the cable car, a leisure cable car, unrelated).

**Stance** = the position of the AUTHOR towards the Heilbronn cable car:
- **support**: the author favours or defends the project.
- **oppose**: the author rejects it, mocks it, calls it a waste, or demands something else instead.
- **neutral**: reports facts without taking a side. Typical for news, even when it quotes critics.
- **mixed**: clearly gives both sides and takes no side, supports the idea but rejects this version, or shows an opinion whose direction cannot be told.

Stance is NOT tone. "Finally! Why did this take so long?!" sounds negative but is support. "A nice idea, but EUR 157 million while the clinic closes" sounds friendly in places but is oppose."""

EVENT_RULES = """Open the source link and compare it with the date, the title and the detail text.
- **confirmed**: the source says this happened, and the date is right (for date precision "month": the month is right).
- **wrong_date**: the event happened but on another date. Enter the correct date and say in the note where you read it.
- **wrong_content**: the source says something different from the title or the detail. Say what is wrong in the note.
- **source_dead**: the link does not open, is behind a wall you cannot pass, or no longer shows the content. If you find a working source, paste it in the note.
The source's own publication date is not always the event date. Check what the text says about when it happened."""

DISPUTE_RULES = """The AI models disagreed about this post. You see all their labels. Decide what is correct.
Use the same rules as in the stance queue: first "is it about the Heilbronn cable car" (yes / passing / no), then the author's stance.
If it is not about the Heilbronn cable car you can also say what it is about instead (project).
Do not simply follow the majority of the models. Read the excerpt and open the link when needed."""


@dataclass(frozen=True)
class QueueSpec:
    name: str
    file: str
    id_col: str
    blind: bool
    title: str
    description: str
    visible: tuple
    hidden: tuple = ()
    estimated_minutes: int = 0
    schema: dict = field(default_factory=dict)


SPECS = {
    "pairs": QueueSpec(
        "pairs", "pair_queue.parquet", "pid", True, "Argument pairs",
        "Do these two claims make the same argument? 120 pairs from the test period, labelled blind.",
        ("pid", "q_claim", "q_project", "c_claim", "c_project"), ("why",), 20,
        {"relation": {"required": True, "values": RELATIONS}}),
    "stance": QueueSpec(
        "stance", "stance_queue.parquet", "doc_id", True, "Heilbronn stance",
        "Is the post about the Heilbronn cable car, and what is the author's stance? Labelled blind.",
        ("doc_id", "date", "channel", "domain", "url", "title", "excerpt"),
        ("model_project", "model_stance", "model_tone", "label_source"), 60,
        {"about": {"required": True, "values": ABOUT},
         "stance": {"required": False, "values": STANCES, "required_when": {"about": ["yes", "passing"]}}}),
    "events": QueueSpec(
        "events", "events_queue.parquet", "event_id", False, "Timeline events",
        "Check each timeline event against its source link.",
        ("event_id", "date", "date_precision", "project", "event_type", "title_en", "detail", "source_url",
         "source_name", "verified"), (), 45,
        {"verdict": {"required": True, "values": VERDICTS},
         "correct_date": {"required": False, "format": "date", "allowed_when": {"verdict": ["wrong_date"]}}}),
    "disputes": QueueSpec(
        "disputes", "disputes_queue.parquet", "doc_id", False, "Disputed classifications",
        "Posts where the AI models disagree. The model labels are shown. Decide the correct label.",
        ("doc_id", "date", "domain", "url", "excerpt"), (), 30,
        {"about": {"required": True, "values": ABOUT},
         "stance": {"required": False, "values": STANCES, "required_when": {"about": ["yes", "passing"]}},
         "project": {"required": False, "values": PROJECTS}}),
}
ORDER = list(SPECS)
# the one field per queue that agreement statistics are computed on first
PRIMARY_KEY = {"pairs": "relation", "stance": "stance", "events": "verdict", "disputes": "stance"}
LABEL_KEYS = {q: list(s.schema) for q, s in SPECS.items()}


def guidelines(queue: str) -> str:
    if queue == "pairs":
        f = config.REPO / "pipeline" / "prompts" / "pair_codebook_v1.md"
        try:
            text = f.read_text(encoding="utf-8").split("Output:")[0]
            body = text.split("\n\n", 2)[2].strip()  # drop the two intro paragraphs written for the model
            return "For each pair: what is the relation between the two claims?\n\n" + body
        except (OSError, IndexError):
            return PAIR_RULES_FALLBACK
    return {"stance": STANCE_RULES, "events": EVENT_RULES, "disputes": DISPUTE_RULES}[queue]


def _clean(v):
    """numpy / pandas scalars -> plain JSON values; NaN -> None"""
    if v is None:
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or v is pd.NaT:
        return None
    return v


class Queue:
    """One loaded queue file. `items` keeps the order of the file."""

    def __init__(self, spec: QueueSpec, df: pd.DataFrame):
        self.spec = spec
        if spec.id_col not in df.columns:
            raise QueueUnavailable(f"queue file {spec.file} has no column {spec.id_col!r}")
        self.df = df.reset_index(drop=True)
        self.model_names = []
        if spec.name == "disputes":
            self.model_names = [c[:-7] for c in df.columns if c.endswith("_stance") and c != "model_stance"]
        self.ids, self.rows = [], {}
        for pos, rec in enumerate(self.df.to_dict("records")):
            rec = {k: _clean(v) for k, v in rec.items()}
            iid = str(rec[spec.id_col])
            if iid in self.rows:
                continue
            rec["_position"] = pos
            self.ids.append(iid)
            self.rows[iid] = rec

    def __len__(self):
        return len(self.ids)

    def __contains__(self, item_id):
        return item_id in self.rows

    def data(self, item_id: str) -> dict:
        """Fields a labeller may always see. For a blind queue this never includes model labels."""
        r = self.rows[item_id]
        d = {c: r.get(c) for c in self.spec.visible if c in r}
        if self.spec.name == "disputes":
            d["models"] = [{"model": m, "project": r.get(f"{m}_project"), "stance": r.get(f"{m}_stance")}
                           for m in self.model_names]
        return d

    def hidden(self, item_id: str) -> dict:
        r = self.rows[item_id]
        return {c: r.get(c) for c in self.spec.hidden if c in r}


_cache: dict = {}


def path(queue: str) -> Path:
    return config.queue_dir() / SPECS[queue].file


def load(queue: str) -> Queue:
    """Read a queue file (cached until the file changes). Raises QueueUnavailable when the file is missing."""
    f = path(queue)
    if not f.exists():
        raise QueueUnavailable(f"queue file not found: {f}")
    st = f.stat()
    key = (str(f), st.st_mtime_ns, st.st_size)
    hit = _cache.get(queue)
    if hit and hit[0] == key:
        return hit[1]
    q = Queue(SPECS[queue], pd.read_parquet(f))
    _cache[queue] = (key, q)
    return q


def available(queue: str) -> bool:
    return path(queue).exists()


def validate_label(queue: str, label) -> dict:
    """Check a label object against the queue's vocabulary. Returns the normalised label (keys in schema order,
    absent optional keys left out). Raises LabelError with a message a person can act on."""
    schema = SPECS[queue].schema
    if not isinstance(label, dict):
        raise LabelError(f"label must be an object with the keys {list(schema)}")
    unknown = [k for k in label if k not in schema]
    if unknown:
        raise LabelError(f"unknown label key(s) {unknown} for queue {queue!r}; allowed: {list(schema)}")
    out = {}
    for key, rule in schema.items():
        v = label.get(key)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, ""):
            if rule.get("required"):
                raise LabelError(f"label.{key} is required; one of {rule.get('values')}")
            continue
        if "values" in rule and v not in rule["values"]:
            raise LabelError(f"label.{key} must be one of {rule['values']}, got {v!r}")
        if rule.get("format") == "date" and not (isinstance(v, str) and DATE_RE.match(v)):
            raise LabelError(f"label.{key} must be a date YYYY-MM-DD or YYYY-MM, got {v!r}")
        out[key] = v
    for key, rule in schema.items():
        for other, vals in rule.get("required_when", {}).items():
            if out.get(other) in vals and key not in out:
                raise LabelError(f"label.{key} is required when {other} is {out.get(other)!r}; one of {rule.get('values')}")
        for other, vals in rule.get("allowed_when", {}).items():
            if key in out and out.get(other) not in vals:
                raise LabelError(f"label.{key} is only allowed when {other} is one of {vals}")
    if queue in ("stance", "disputes") and out.get("about") == "no":
        out.pop("stance", None)  # a post that is not about the project has no stance towards it
    return out
