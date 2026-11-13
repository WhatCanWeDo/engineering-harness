"""Deterministic lifecycle glue. Native agents supply selection/proposal JSON."""
import json
from pathlib import Path

from .knowledge import KnowledgeError, fail, string_list, positive


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


def sync_index(store):
    try:
        return store.index_sync()
    except KnowledgeError:
        return {"status": "error", "warning": "Index update failed; search will use explicit fallback"}


def start(store, binding, output, mode="lexical", retrieval="legacy"):
    if retrieval not in {"legacy", "staged"}:
        fail("validation", "Unknown retrieval workflow")
    binding = dict(binding)
    task_paths = binding.pop("paths", None)
    from . import subprojects
    if task_paths is not None: task_paths = subprojects.normalize_paths(task_paths)
    bound = store.db.execute("SELECT value FROM meta WHERE key='project_id'").fetchone()
    if bound and binding.get("project_id", bound[0]) != bound[0]:
        fail("forbidden", "Database belongs to a different project")
    if bound and "project_id" not in binding: binding["project_id"] = bound[0]
    directory = new_directory(output)
    # Pending knowledge must be committed before freezing the receiving snapshot.
    reconciliation = store.reconcile()
    index = sync_index(store)
    previous = subprojects.get_route(store, binding["task_id"])
    root = getattr(store, "project_root", None)
    root_matches = not getattr(store, "project_id", None) or store.project_id == binding["project_id"]
    if not root_matches: root = None
    already_started = store.db.execute("SELECT 1 FROM tasks WHERE task_id=?", (binding["task_id"],)).fetchone()
    if previous is None and already_started:
        # A legacy task must not acquire a taxonomy learned after its snapshot.
        cat = {"revision": None, "groups": [], "inventory": {"method":"legacy_task","complete":False}}
    else:
        cat = subprojects.refresh(store, binding["project_id"], root) if previous is None else None
    task = store.begin_task(**binding)
    relative_cwd = None
    if root:
        try:
            relative_cwd = Path.cwd().resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError: pass
    organization = subprojects.attach(store, task["task_id"], cat, task_paths, relative_cwd)
    task["subprojects"] = subprojects.summarize(organization)
    write_json(directory / "task.json", task)
    from .freshness import brief as maintenance_brief
    maintenance = maintenance_brief(store, task["task_id"]) if "developer" in task["roles"] else None
    maintenance_path = None
    if maintenance and maintenance["due"]:
        maintenance_path = str((directory / "maintenance.json").absolute())
        write_json(directory / "maintenance.json", maintenance)
    paths, planner_paths = {}, {}
    for role in task["roles"]:
        if retrieval == "staged":
            path = directory / f"planner-{role}.json"
            write_json(path, store.retrieval_plan_brief(task["task_id"], role))
            planner_paths[role] = str(path.absolute())
            continue
        path = directory / f"scout-{role}.json"
        brief = store.scout_brief(task["task_id"], role, mode=mode)
        if getattr(store, "project_root", None) and getattr(store, "project_id", None) in (None, task["project_id"]):
            from .projects import navigation
            brief["project_navigation"] = navigation(store.project_root, task["goal"])
        write_json(path, brief)
        paths[role] = str(path.absolute())
    return {"task_id": task["task_id"], "output": str(directory.absolute()),
            "brief_paths": paths, "planner_paths": planner_paths, "retrieval": retrieval,
            "maintenance_path": maintenance_path, "maintenance_due": maintenance["due"] if maintenance else None, "reconciliation": reconciliation, "index": index, "subprojects": subprojects.summarize(organization)}


def retrieve(store, task, role, plan, output, mode="semantic", candidate_limit=20, experimental=False):
    directory = new_directory(output)
    result = store.retrieve(task, plan, role, mode, candidate_limit, experimental)
    path = directory / "retrieval.json"
    write_json(path, result)
    # Native reranker sees neither hypothetical answers nor fusion scores/plans.
    brief = {k: result[k] for k in ("retrieval_id", "task_id", "role", "goal", "candidates", "prompt", "warnings")}
    reranker_path = directory / "reranker.json"
    write_json(reranker_path, brief)
    return {"retrieval_id": result["retrieval_id"], "status": result["status"],
            "retrieval_path": str(path.absolute()), "reranker_path": str(reranker_path.absolute()),
            "plan_digest": result["plan_digest"], "candidates": len(result["candidates"]),
            "warnings": result["warnings"]}


def rerank(store, task, role, selection, output, budget=1200, top_k=5):
    result = store.apply_rerank(task, selection, role, top_k)
    packet = store.prepare_context(task, role=role, budget=budget,
                                   selected_refs=result["selected_refs"], selection_trace=result)
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    packet_path = directory / f"{packet['packet_id']}.json"
    text_path = directory / f"{packet['packet_id']}.txt"
    write_json(packet_path, packet)
    with text_path.open("x", encoding="utf-8") as stream:
        stream.write(packet["text"])
    return {"packet_id": packet["packet_id"], "packet_path": str(packet_path.absolute()),
            "text_path": str(text_path.absolute()), "retrieval_id": result["retrieval_id"],
            "status": result["status"], "mode": result["mode"], "warnings": packet["warnings"]}


def context(store, task, role, selection, output, budget):
    if not isinstance(selection, dict) or "selected_refs" not in selection:
        fail("validation", "Scout output must contain selected_refs")
    from .subprojects import refine, summarize
    # Validate source selection before freezing the shared routing hint.
    binding = store.get_task(task); store._role(binding, role)
    positive(budget, "budget")
    for ref in string_list(selection["selected_refs"], "selected_refs"): store._context_record(binding, role, ref)
    organization = refine(store, task, role, selection.get("subproject_ids"))
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
            "text_path": str(text_path.absolute()), "subprojects": summarize(organization)}


def finish(store, task, outcome, output):
    directory = new_directory(output)
    queued = store.finish_task(task, outcome)
    reconciliation = store.reconcile()
    path = directory / "curator.json"
    write_json(path, store.curator_brief(task))
    return {"job_id": queued["job_id"], "curator_path": str(path.absolute()),
            "reconciliation": reconciliation}


def ingest(store, task, proposals, batch):
    queued = store.propose(task, proposals, batch)
    reconciliation = store.reconcile()
    from .subprojects import refresh
    project = store.get_task(task)["project_id"]
    root = getattr(store, "project_root", None) if getattr(store, "project_id", None) in (None, project) else None
    organization = refresh(store, project, root)
    return {"enqueue": queued, "reconciliation": reconciliation, "index": sync_index(store),
            "subprojects_revision": organization["revision"]}
