"""python -m citypulse.batch <file.json|file.csv> [--json]

Processes one file in the foreground and prints the step table. The file is left where it is.
Exit code: 0 done, 1 done with errors, 2 failed or duplicate."""
import json, sys
from . import process_sync, step_table, DuplicateUpload


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        run = process_sync(args[0])
    except DuplicateUpload as e:
        print(f"{e}. Nothing was processed.")
        return 2
    except OSError as e:
        print(f"cannot read {args[0]}: {e}")
        return 2
    if "--json" in argv:
        print(json.dumps(run, ensure_ascii=False, indent=1))
    else:
        print(f"run {run['run_id']}  {run['filename']}  status: {run['status']}  {run['message']}")
        print(step_table(run))
        print("counts:", json.dumps(run["counts"]))
        print("models:", json.dumps(run["models"], ensure_ascii=False))
        for e in run["errors"]:
            print(f"  problem [{e['step']}] {e['record']}: {e['message']}")
        for c in run["findings"]["concerns"]:
            print(f"  concern [{c.get('state')}] {c.get('label')} ({c.get('n_claims')} claims, {c.get('n_voices')} voices)")
        if run["findings"].get("note"):
            print("  findings note:", run["findings"]["note"])
    return {"done": 0, "done_with_errors": 1}.get(run["status"], 2)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
