"""Descriptive paired analysis. Missing measurements never become zero."""
from collections import Counter, defaultdict
import html
import json
from pathlib import Path
from statistics import mean
from .core import digest, require, put, read
from .review import validate_review


def accounting(exp, rid=None, phase='f0'):
    usage = [v for v in exp.records('usage', rid) if v.get('run_id') == rid and v['phase'] == phase]
    totals = defaultdict(float)
    for u in usage:
        if u['money'] is not None: totals[u['currency']] += u['money']
    executions = exp.records('execution', rid) if rid else []
    expected = {digest(k) for k in executions[0]['request_keys']} if executions else set()
    actual = {digest([u['provider'], u['request_id']]) for u in usage}
    inventory = bool(executions and executions[0]['accounting_complete'] and actual == expected)
    complete = inventory and len(totals) == 1 and all(u['money'] is not None for u in usage)
    # No observed request records cannot substantiate a zero cost.
    complete = complete and bool(usage)
    return {'known_subtotal': dict(totals), 'known_records': sum(u['money'] is not None for u in usage), 'records': len(usage), 'expected_records': len(expected) if executions else None, 'inventory_complete': inventory, 'complete': complete, 'money': next(iter(totals.values())) if complete else None, 'currency': next(iter(totals)) if complete else None, 'basis_counts': dict(Counter(u['basis'] for u in usage))}


def run_summary(exp, run):
    rid = run['run_id']; execution = exp.records('execution', rid); evaluations = exp.records('evaluation', rid)
    f0 = next((e for e in evaluations if e['revision'] == 'F0'), None)
    f1 = next((e for e in evaluations if e['revision'] == 'F1'), None)
    review = exp.records('review', rid)
    review = review[0] if review else None
    receipt = execution[0] if execution else None
    correctness = None
    if receipt:
        if receipt['status'] in ('timeout', 'budget_exhausted', 'aborted'): correctness = False
        elif receipt['status'] == 'completed' and f0:
            verdicts = [c['verdict'] for c in f0['checks']]
            if 'fail' in verdicts: correctness = False
            elif all(v == 'pass' for v in verdicts): correctness = True
    total = validate_review(review, exp.plan['limits']['human_seconds_per_review']) if review else None
    measured = total is not None and review['stop_reason'] == 'completed'
    return {**run, 'status': receipt['status'] if receipt else 'missing', 'isolation': receipt['isolation'] if receipt else None, 'correctness': correctness, 'evaluation': f0, 'after_repair': f1, 'cost': accounting(exp, rid), 'repair_cost': accounting(exp, rid, 'repair'), 'human_seconds': sum(total.values()) if measured else None, 'time_components': total, 'review_censored': bool(review and review['stop_reason'] != 'completed'), 'review': review, 'corrections': len(review['issues']) if measured else None, 'repair_rounds': sum(i['rounds'] for i in review['issues']) if measured else None, 'review_planned': run['replicate'] in exp.plan['review']['replicates']}


def compare(exp):
    integrity = []
    try:
        exp.verify_inputs()
        for run in exp.plan['schedule']:
            for revision in ('F0', 'F1'):
                if (exp.path / 'outputs' / run['run_id'] / revision).exists(): exp.output(run['run_id'], revision)
    except (ValueError, OSError) as exc:
        integrity.append(str(exc))
    runs = [run_summary(exp, r) for r in exp.plan['schedule']]
    pairs = []
    grouped = defaultdict(dict)
    for r in runs: grouped[(r['task_key'], r['replicate'])][r['arm']] = r
    counts = Counter()
    for (task, rep), arms in grouped.items():
        a, b = arms['A'], arms['B']
        ca, cb = a['correctness'], b['correctness']
        outcome = 'missing' if ca is None or cb is None else ('both_pass' if ca and cb else 'only_A' if ca else 'only_B' if cb else 'both_fail')
        counts[outcome] += 1
        human = b['human_seconds'] - a['human_seconds'] if a['human_seconds'] is not None and b['human_seconds'] is not None else None
        cost = b['cost']['money'] - a['cost']['money'] if a['cost']['money'] is not None and b['cost']['money'] is not None and a['cost']['currency'] == b['cost']['currency'] else None
        corrections = b['corrections'] - a['corrections'] if a['corrections'] is not None and b['corrections'] is not None else None
        pairs.append({'task_key': task, 'replicate': rep, 'A': a['run_id'], 'B': b['run_id'], 'outcome': outcome, 'human_delta': human, 'cost_delta': cost, 'currency': a['cost']['currency'] if cost is not None else None, 'corrections_delta': corrections})
    primary = exp.plan['analysis']['primary']
    eligible = [p for p in pairs if primary == 'cost' or p['replicate'] in exp.plan['review']['replicates']]
    field = 'human_delta' if primary == 'human_seconds' else 'cost_delta'
    task_deltas = {}
    for task in exp.plan['tasks']:
        rows = [p for p in eligible if p['task_key'] == task['key']]
        task_deltas[task['key']] = mean(p[field] for p in rows) if rows and all(p[field] is not None for p in rows) else None
    currencies = {p['currency'] for p in eligible if p['cost_delta'] is not None}
    primary_complete = all(v is not None for v in task_deltas.values()) and (primary != 'cost' or len(currencies) == 1)
    delta = mean(task_deltas.values()) if primary_complete else None
    isolation = all(r['isolation'] == 'attested' for r in runs)
    violated = any(r['isolation'] == 'violated' for r in runs)
    # Reviewer protocol is a recorded condition, never inferred from a neutral label.
    if exp.plan['review']['protocol'] == 'independent_reviewers':
        exposures = defaultdict(list)
        for r in runs:
            if r['review']:
                q = r['review']; exposures[(r['task_key'], q['reviewer'])].append(r['run_id'])
                if q['prior_exposure']: integrity.append('Independent reviewer declared prior exposure')
        if any(len(v) > 1 for v in exposures.values()): integrity.append('Reviewer saw multiple variants/repeats of same task')
    planned_review = [r for r in runs if r['review_planned']]
    measurements_complete = all(r['human_seconds'] is not None for r in planned_review) and all(r['cost']['complete'] for r in runs)
    if integrity or violated: decision = 'invalid'
    elif counts['only_A']: decision = 'regression_observed'
    elif any(r['correctness'] is None for r in runs) or not primary_complete or not measurements_complete: decision = 'incomplete'
    elif not isolation or counts['both_fail'] or delta > -exp.plan['analysis']['min_improvement']: decision = 'inconclusive'
    else: decision = 'promising_on_dev' if exp.plan['dataset'] == 'development' else 'recommend_pilot'
    if exp.plan.get('synthetic'): decision = 'synthetic_demonstration'
    return {'version': 1, 'synthetic': exp.plan.get('synthetic', False), 'analysis_version': exp.plan['analysis_version'], 'experiment_sha256': digest(exp.plan), 'hypothesis': exp.plan['hypothesis'], 'decision': decision, 'planned_runs': len(runs), 'received_runs': sum(r['status'] != 'missing' for r in runs), 'planned_pairs': len(pairs), 'correctness_matrix': {k: counts[k] for k in ('both_pass', 'only_A', 'only_B', 'both_fail', 'missing')}, 'primary': primary, 'primary_delta_B_minus_A': delta, 'task_level_deltas': task_deltas, 'complete_primary_pairs': sum(p[field] is not None for p in eligible), 'planned_primary_pairs': len(eligible), 'planned_reviews': len(planned_review), 'completed_reviews': sum(r['human_seconds'] is not None for r in planned_review), 'censored_reviews': sum(r['review_censored'] for r in runs), 'integrity_errors': integrity, 'runs': runs, 'pairs': pairs, 'overhead': accounting(exp, None, 'overhead'), 'limitations': ['Local cooperative profile: filesystem isolation and receipts are not independently enforced.', 'Per-run time/call/money limits are advisory in native manual sessions.', 'No p-values or equivalence claim; task-level means avoid counting replicates as independent tasks.', 'Personal crossover can retain learning/carryover despite neutral labels.', 'Cost inventory and independence are attested; no provider-billing integration.', 'Private backend unavailable; candidate is never installed automatically.']}


def report(exp, destination):
    result = compare(exp)
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=False)
    put(destination / 'comparison.json', result)
    esc = lambda x: html.escape(str(x))
    def val(x): return '—' if x is None else f'{x:.2f}' if isinstance(x, float) else esc(x)
    def table(headers, rows):
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+esc(h)+'</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows) + '</tbody></table></div>'
    pair_table = table(['Задача / повтор', 'Correctness F0', 'Δ human, sec', 'Δ cost', 'Δ corrections'], [[esc(p['task_key'])+' / '+str(p['replicate']),esc(p['outcome']),val(p['human_delta']),val(p['cost_delta'])+' '+esc(p['currency'] or ''),val(p['corrections_delta'])] for p in result['pairs']])
    run_table = table(['Run / arm','Статус','F0','Human, sec','Corrections / rounds','Известная стоимость F0','Учтённые вызовы'], [[esc(r['run_id'][:8])+' / '+r['arm'],esc(r['status']),val(r['correctness']),val(r['human_seconds'])+(' (censored)' if r['review_censored'] else ''),val(r['corrections'])+' / '+val(r['repair_rounds']),esc(json.dumps(r['cost']['known_subtotal']))+(' ✓' if r['cost']['complete'] else ' (partial/unknown)'),str(r['cost']['records'])+' / '+val(r['cost']['expected_records'])] for r in result['runs']])
    cards = ''.join(f'<div><b>{esc(k)}</b><strong>{v}</strong></div>' for k,v in result['correctness_matrix'].items())
    content = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Harness A/B</title><style>body{{font:16px/1.6 system-ui;color:#142238;background:#f5f7fa;max-width:1050px;margin:auto;padding:24px}}h1{{font-size:2.3rem}}section{{background:white;border-radius:14px;padding:24px;margin:20px 0}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dfe5ec;min-width:95px}}th{{font-size:.85rem}}.cards{{display:flex;flex-wrap:wrap;gap:14px}}.cards div{{flex:1;background:#eaf1f7;padding:16px;border-radius:10px}}strong{{display:block;font-size:2rem}}code,pre{{overflow-wrap:anywhere;white-space:pre-wrap}}.badge{{padding:8px 16px;background:#e0eafa;display:inline-block;border-radius:20px}}@media(max-width:600px){{body{{padding:12px}}section{{padding:16px}}}}</style><h1>Harness A/B</h1><p>{esc(result['hypothesis'])}</p><p class="badge">{esc(result['decision'])}</p><section><h2>Полнота и correctness</h2><p>Получено {result['received_runs']} / {result['planned_runs']} запусков. Review: {result['completed_reviews']} / {result['planned_reviews']}; censored: {result['censored_reviews']}.</p><div class="cards">{cards}</div></section><section><h2>Парные изменения B − A</h2><p>Основная метрика: {esc(result['primary'])}; среднее по задачам: {val(result['primary_delta_B_minus_A'])}. Отрицательное значение — уменьшение затрат. Отсутствующие данные показаны тире.</p>{pair_table}</section><section><h2>Все назначенные запуски</h2>{run_table}<p>Стоимость — известный subtotal, пока inventory и billing неполны. Общие расходы эксперимента: {esc(json.dumps(result['overhead']['known_subtotal']))}; записей {result['overhead']['records']}. Детальные phases, F1, исходные receipts и checks сохранены в comparison.json.</p></section><section><h2>Границы вывода</h2><ul>{''.join('<li>'+esc(x)+'</li>' for x in result['integrity_errors']+result['limitations'])}</ul><p>Это описательное сравнение. Решение о применении новой версии принимает человек.</p></section></html>'''
    (destination / 'report.html').write_text(content)
    return {'output': str((destination / 'report.html').resolve()), 'comparison': str((destination / 'comparison.json').resolve()), 'decision': result['decision']}
