"""Deterministic lifecycle glue. Native agents supply selection/proposal JSON."""
import json
from pathlib import Path

from .knowledge import fail


def new_directory(path):
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        fail("output_exists", "Output directory already exists; choose a new path")
    return path


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def start(store, binding, output):
    directory = new_directory(output)
    # Pending knowledge must be committed before freezing the receiving snapshot.
    reconciliation = store.reconcile()
    task = store.begin_task(**binding)
    write_json(directory / "task.json", task)
    paths = {}
    for role in task["roles"]:
        path = directory / f"scout-{role}.json"
        write_json(path, store.scout_brief(task["task_id"], role))
        paths[role] = str(path.absolute())
    return {"task_id": task["task_id"], "output": str(directory.absolute()),
            "brief_paths": paths, "reconciliation": reconciliation}


def context(store, task, role, selection, output, budget):
    if not isinstance(selection, dict) or "selected_refs" not in selection:
        fail("validation", "Scout output must contain selected_refs")
    packet = store.prepare_context(task, role=role, budget=budget,
                                   selected_refs=selection["selected_refs"])
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    packet_path = directory / f"{packet['packet_id']}.json"
    text_path = directory / f"{packet['packet_id']}.txt"
    write_json(packet_path, packet)
    with text_path.open("x", encoding="utf-8") as stream:
        stream.write(packet["text"])
    return {"packet_id": packet["packet_id"], "packet_path": str(packet_path.absolute()),
            "text_path": str(text_path.absolute())}


def finish(store, task, outcome, output):
    directory = new_directory(output)
    queued = store.finish_task(task, outcome)
    reconciliation = store.reconcile()
    path = directory / "curator.json"
    write_json(path, store.curator_brief(task))
    return {"job_id": queued["job_id"], "curator_path": str(path.absolute()),
            "reconciliation": reconciliation}


def ingest(store, task, proposals, batch):
    return {"enqueue": store.propose(task, proposals, batch),
            "reconciliation": store.reconcile()}
