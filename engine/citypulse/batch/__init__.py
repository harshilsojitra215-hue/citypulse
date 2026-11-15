"""New-batch workflow: a file of new public posts goes in, new posts and arguments appear in the application.

    from citypulse import batch
    run = batch.submit(path, filename)      # returns at once, status "queued"; raises batch.DuplicateUpload (.run_id)
    batch.get_run(run["run_id"])            # poll: steps, counts, errors, findings
    batch.list_runs()                       # newest first
    batch.template()                        # field list and example for the upload dialog
    batch.process_sync(path, filename)      # same workflow without a thread (tests, command line)

Command line: python -m citypulse.batch <file.json|file.csv>

Steps: validate, clean, dedupe, relevance, classify, extract, match, novelty, store. Cleaning, the keyword rules,
the codebook prompt and the model caller are the research pipeline's own code (see steps.py).
"""
from .formats import template, UnusableFile
from .steps import LLMUnavailable
from .runs import submit, process_sync, list_runs, get_run, step_table, DuplicateUpload, STEP_NAMES

__all__ = ["submit", "process_sync", "list_runs", "get_run", "template", "step_table", "DuplicateUpload", "UnusableFile",
           "LLMUnavailable", "STEP_NAMES"]
