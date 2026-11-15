import os, sqlite3, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE)
LOGS = os.path.join(HERE, 'logs')
sys.path.insert(0, LIVE)
os.makedirs(LOGS, exist_ok=True)


class Tee:
    """Print to the console and to a log file."""
    def __init__(self, name):
        self.f = open(os.path.join(LOGS, name), 'w', encoding='utf-8')

    def __call__(self, *a):
        s = ' '.join(str(x) for x in a)
        print(s)
        self.f.write(s + '\n')
        self.f.flush()


def items(db):
    c = sqlite3.connect(os.path.join(LIVE, 'data', db))
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute('SELECT * FROM items')]
