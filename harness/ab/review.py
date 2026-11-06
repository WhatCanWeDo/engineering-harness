"""Human-only review recorder: local browser persistence and explicit JSON export."""
import html
import json
from pathlib import Path
from .core import require, text, number


def validate_review(value, cap):
    text(value.get('reviewer'), 'reviewer')
    require(type(value.get('prior_exposure')) is bool and type(value.get('unblinded')) is bool, 'Exposure/unblinding booleans required')
    require(type(value.get('review_order')) is int and value['review_order'] > 0, 'review_order required')
    require(value.get('verdict') in ('accept', 'changes_requested', 'undecided'), 'Review verdict required')
    require(value.get('stop_reason') in ('completed', 'abandoned', 'capped'), 'stop_reason required')
    events = value.get('events')
    require(isinstance(events, list) and events, 'Timer events required')
    active, last, totals, stopped = None, -1, {'review': 0, 'repair': 0, 'intervention': 0}, False
    for i, event in enumerate(events):
        require(not stopped, 'Events after stop')
        t = number(event.get('at_ms'), 'event at_ms')
        require(t >= last, 'Non-monotonic timer events')
        if active:
            totals[active] += (t - last) / 1000
        action = event.get('action')
        if action in ('start', 'resume'):
            require(active is None and ((i == 0) == (action == 'start')), 'Invalid start/resume')
            require(event.get('mode') in totals, 'Invalid timer mode')
            active = event['mode']
        elif action == 'pause':
            require(active is not None, 'Pause needs active timer')
            active = None
        elif action == 'stop':
            require(i > 0, 'Stop needs started timer')
            active = None; stopped = True
        else:
            require(False, 'Unknown timer event')
        last = t
    require(stopped, 'Final stop event required')
    require(value['stop_reason'] != 'completed' or sum(totals.values()) <= cap, 'Over-cap review must be marked capped')
    issues = value.get('issues')
    require(isinstance(issues, list), 'issues required; use [] only after actual review')
    ids = set()
    for issue in issues:
        ident = text(issue.get('issue_id'), 'issue_id')
        require(ident not in ids, 'Duplicate issue IDs'); ids.add(ident)
        require(issue.get('severity') in ('minor', 'major', 'critical'), 'Issue severity required')
        require(issue.get('kind') in ('human_edit', 'agent_repair_request'), 'Issue kind required')
        require(type(issue.get('rounds')) is int and issue['rounds'] >= 1, 'Issue rounds must be positive integer')
        text(issue.get('summary'), 'issue summary')
    if value['verdict'] == 'accept':
        require(not issues, 'Accept with corrections is ambiguous; use changes_requested')
    return totals


def render_review(exp, rid, output):
    run = exp.run(rid)
    require(run['replicate'] in exp.plan['review']['replicates'], 'Run outside review subset')
    tree, manifest = exp.output(rid)
    task = exp.task(run)
    previews = []
    for name in manifest['files']:
        data = (tree / name).read_bytes()[:100000]
        try: content = data.decode('utf-8')
        except UnicodeDecodeError: content = '[Binary artifact — inspect frozen file with appropriate viewer]'
        previews.append(f'<details><summary>{html.escape(name)}</summary><pre>{html.escape(content)}</pre></details>')
    payload = {'version': 1, 'run_id': rid, 'output_sha256': manifest['digest'], 'cap': exp.plan['limits']['human_seconds_per_review']}
    source = Path(__file__).with_name('review.html').read_text()
    source = source.replace('@@DATA@@', json.dumps(payload).replace('<', '\\u003c'))
    source = source.replace('@@TASK@@', html.escape(task['goal'])).replace('@@FILES@@', ''.join(previews))
    source = source.replace('@@REQUIREMENTS@@', html.escape(', '.join(task['requirements'])))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream: stream.write(source)
    return {'output': str(output.resolve()), 'label': rid[:8], 'storage': 'browser_localStorage; export JSON then ingest', 'blinding': 'neutral label, contents may reveal treatment; coordinator knows mapping'}
