"""CLI shared by `harness ab` and portable skill wrapper."""
from pathlib import Path
from .core import Experiment, plan, read, require, put, digest, now


def register(commands):
    root = commands.add_parser('ab', help='Local paired skill/workflow comparison; no agent loop')
    sub = root.add_subparsers(dest='ab_action', required=True)
    p = sub.add_parser('plan'); p.add_argument('--input', required=True); p.add_argument('--output', required=True)
    for action in ('prepare', 'dispatch', 'freeze', 'ingest', 'evaluate', 'review', 'report', 'status', 'receipt', 'close'):
        p = sub.add_parser(action); p.add_argument('--experiment', required=True)
        if action in ('freeze', 'evaluate', 'review', 'receipt'): p.add_argument('--run', required=True)
        if action in ('freeze', 'evaluate'): p.add_argument('--revision', choices=['F0', 'F1'], default='F0')
        if action == 'close': p.add_argument('--reason', required=True)
        if action == 'freeze':
            p.add_argument('--source', required=True); p.add_argument('--files', required=True, help='JSON array of explicit relative file paths')
        if action == 'ingest':
            p.add_argument('--kind', required=True, choices=['execution', 'usage', 'evaluation', 'review']); p.add_argument('--input', required=True)
        if action in ('review', 'report'): p.add_argument('--output', required=True)
    return root


def dispatch(args):
    if args.ab_action == 'plan': return plan(read(args.input), args.output)
    exp = Experiment(args.experiment)
    with exp.lock():
        if args.ab_action not in ('report', 'status', 'close', 'receipt'):
            require(not (exp.path / 'closed.json').exists(), 'Experiment is closed; records remain immutable')
        if args.ab_action == 'close':
            require(bool(args.reason.strip()), 'Close reason required')
            if (exp.path / 'closed.json').exists(): return read(exp.path / 'closed.json')
            value = {'experiment_sha256': digest(exp.plan), 'closed_at': now(), 'reason': args.reason, 'knowledge_publication': 'not_performed; curate experiment evidence separately'}
            put(exp.path / 'closed.json', value)
            return value
        if args.ab_action == 'receipt': return exp.receipt(args.run)
        if args.ab_action == 'prepare': return exp.prepare()
        if args.ab_action == 'dispatch': return exp.dispatch()
        if args.ab_action == 'freeze': return exp.freeze(args.run, args.source, read(args.files), args.revision)
        if args.ab_action == 'ingest': return exp.ingest(args.kind, read(args.input))
        if args.ab_action == 'evaluate':
            from .evaluate import evaluate
            return evaluate(exp, args.run, args.revision)
        if args.ab_action == 'review':
            from .review import render_review
            return render_review(exp, args.run, args.output)
        if args.ab_action == 'report':
            from .analysis import report
            return report(exp, args.output)
        from .analysis import compare
        result = compare(exp)
        return {k: v for k, v in result.items() if k not in ('runs', 'pairs')}
