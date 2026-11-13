"""R3/R4 public contract suite authored before target implementation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from harness.knowledge import KnowledgeError, KnowledgeStore


class Provider:
    model_id = 'staged-contract/v1'
    dimensions = 3
    def __init__(self):
        self.calls = []
        self.hook = None
    def embed(self, texts, kind='document'):
        texts = list(texts)
        self.calls.append((kind, texts))
        if self.hook:
            self.hook(kind)
        return [[1., 0., 0.] for _ in texts]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'store.sqlite3'
        self.provider = Provider()
        self.s = KnowledgeStore(self.db, embedder=self.provider)
        self.s.project_root = self.root
        self.addCleanup(lambda: self.s.close())
        self.serial = 0
    def publish(self, title, project='p', symbols=None, dependencies=None):
        self.serial += 1
        task = 'seed-' + str(self.serial)
        self.s.begin_task(task, project, 'publish')
        f = self.root / (task + '.txt')
        claim = title + ' documented observation'
        f.write_text(claim)
        eid = self.s.add_evidence(task, str(f))['evidence_id']
        self.s.finish_task(task, {'status': 'success', 'evidence_ids': [eid]})
        proposal = dict(title=title, claim=claim, kind='observation', symbols=symbols or [], evidence_ids=[eid], basis={'evidence_id': eid, 'quote': claim})
        if dependencies:
            proposal['dependencies'] = dependencies
        self.s.propose(task, [proposal], 'batch')
        refs = [ref for r in self.s.reconcile()['receipts'] for ref in r.get('entry_refs', [])]
        self.assertEqual(len(refs), 1)
        return refs[0]
    def task(self, goal='alpha', task='query', project='p'):
        self.s.begin_task(task, project, goal)
        return task
    @staticmethod
    def refs(brief):
        return [r['entry_ref'] for r in brief['candidates']]
    def plan(self, task='query', **changes):
        result = dict(version=1, task_id=task, role='developer', original=self.s.get_task(task)['goal'], subqueries=[], reason='public deterministic plan')
        result.update(changes)
        return result
    def retrieve(self, task='query', **kwargs):
        return self.s.retrieve(task, mode='lexical', **kwargs)
    def selection(self, brief, refs=None, abstain=False):
        return dict(retrieval_id=brief['retrieval_id'], ranked_refs=self.refs(brief) if refs is None else refs, abstain=abstain)


class StagedContractTests(Fixture):
    def test_query_only_planner_and_persisted_original_fallback(self):
        ref = self.publish('alpha')
        self.task()
        before = self.s.export_project('p')
        planner = self.s.retrieval_plan_brief('query')
        for field in ('goal', 'prompt', 'limits', 'binding'):
            self.assertIn(field, planner)
        self.assertEqual(planner['goal'], 'alpha')
        self.assertEqual(self.provider.calls, [])
        brief = self.retrieve()
        for field in ('retrieval_id', 'task_id', 'role', 'snapshot_seq', 'policy_revision', 'plan_digest', 'candidates', 'prompt', 'warnings', 'status'):
            self.assertIn(field, brief)
        self.assertEqual(self.refs(brief), [ref])
        self.assertTrue(brief['warnings'])
        self.assertEqual(brief['snapshot_seq'], self.s.get_task('query')['snapshot_seq'])
        self.assertEqual(brief['policy_revision'], self.s.get_task('query')['policy_revision'])
        self.assertEqual(self.s.export_project('p'), before)
        self.s.close()
        self.s = KnowledgeStore(self.db, embedder=self.provider)
        result = self.s.apply_rerank('query', {'retrieval_id': brief['retrieval_id']})
        self.assertEqual(result['selected_refs'], [ref])
        self.assertEqual(result['mode'], 'retrieval_fallback')
        self.assertFalse(result['abstained'])

    def test_plan_validation(self):
        self.task()
        invalid = [dict(version=True), dict(version=2), dict(task_id='other'), dict(role='public'), dict(original='changed'), dict(rewrite=''), dict(rewrite=' '), dict(rewrite='x'*1001), dict(rewrite=3), dict(subqueries='alpha'), dict(subqueries=['']), dict(subqueries=['x']*4), dict(subqueries=['x'*1001]), dict(hypothetical_document=''), dict(hypothetical_document='x'*1501), dict(reason='x'*1001), dict(reason=1), dict(extra='unknown')]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(KnowledgeError):
                self.retrieve(plan=self.plan(**changes), experimental=True)
        for key in ('version', 'task_id', 'role', 'original'):
            plan = self.plan(); del plan[key]
            with self.subTest(missing=key), self.assertRaises(KnowledgeError):
                self.retrieve(plan=plan)
        for changes in (dict(subqueries=['extra']), dict(hypothetical_document='extra')):
            with self.subTest(experimental=changes), self.assertRaises(KnowledgeError):
                self.retrieve(plan=self.plan(**changes))
        for limit in (0, 31, True, 1.5, '2'):
            with self.subTest(limit=limit), self.assertRaises(KnowledgeError):
                self.retrieve(candidate_limit=limit)
        for mode in ('unknown', '', None):
            with self.subTest(mode=mode), self.assertRaises(KnowledgeError):
                self.s.retrieve('query', mode=mode)

    def test_original_first_dedup_rrf_and_exact_precedence(self):
        a = self.publish('alpha shared', symbols=['alpha'])
        b = self.publish('beta shared')
        c = self.publish('beta extra')
        self.task()
        queries = ['alpha', 'beta']
        rankings = [[r['entry_id']+'@'+str(r['revision']) for r in self.s.search('query', q)['results']] for q in queries]
        scores = {}
        for ranking in rankings:
            for i, ref in enumerate(ranking, 1): scores[ref] = scores.get(ref, 0) + 1/(60+i)
        expected = [a] + [r for r in sorted(scores, key=lambda r: (-scores[r], r)) if r != a]
        calls = []
        original = self.s.search
        def observed(task, query, *args, **kwargs):
            calls.append(query)
            return original(task, query, *args, **kwargs)
        with patch.object(self.s, 'search', side_effect=observed):
            brief = self.retrieve(plan=self.plan(rewrite='beta', subqueries=['alpha','beta']), experimental=True)
        self.assertEqual(calls, queries)
        self.assertEqual(self.refs(brief), expected)
        self.assertEqual(len(self.refs(brief)), 3)
        self.assertEqual(self.refs(self.retrieve(plan=self.plan(rewrite='beta'), candidate_limit=1)), [a])

    def test_hyde_uses_document_encoding_and_distinct_cache_kind(self):
        self.publish('alpha')
        self.s.index_sync()
        self.task(goal='same text')
        self.provider.calls.clear()
        self.s.search('query', 'same text', mode='semantic')
        self.s.retrieve('query', plan=self.plan(hypothetical_document='same text'), experimental=True)
        self.assertIn(('query', ['same text']), self.provider.calls)
        self.assertIn(('document', ['same text']), self.provider.calls)

    def test_rerank_strict_validation_and_bounds(self):
        self.publish('alpha'); self.task()
        brief = self.retrieve(); good = self.selection(brief)
        invalid = [dict(extra=1), dict(ranked_refs='bad'), dict(ranked_refs=[self.refs(brief)[0]]*2), dict(ranked_refs=['K-invented@1']), dict(ranked_refs=[]), dict(abstain=True), dict(abstain=0), dict(reason='x'*1001), dict(reason=0), dict(retrieval_id='absent')]
        for changes in invalid:
            response = {**good, **changes}
            with self.subTest(changes=changes), self.assertRaises(KnowledgeError):
                self.s.apply_rerank('query', response)
        for missing in ('ranked_refs', 'abstain', 'retrieval_id'):
            response = dict(good); del response[missing]
            with self.subTest(missing=missing), self.assertRaises(KnowledgeError):
                self.s.apply_rerank('query', response)
        for top_k in (0, 9, True, 1.5, '2'):
            with self.subTest(top_k=top_k), self.assertRaises(KnowledgeError):
                self.s.apply_rerank('query', good, top_k=top_k)

    def test_native_order_abstention_empty_and_current_revalidation(self):
        refs = [self.publish('alpha '+suffix) for suffix in ('one','two','three')]
        self.task(); brief = self.retrieve()
        order = list(reversed(self.refs(brief)))
        chosen = self.s.apply_rerank('query', self.selection(brief, order), top_k=2)
        self.assertEqual(chosen['selected_refs'], order[:2]); self.assertEqual(chosen['mode'], 'native_rerank')
        self.assertEqual(chosen['plan_digest'], brief['plan_digest']); self.assertEqual(chosen['retrieval_id'], brief['retrieval_id'])
        self.assertFalse(chosen['abstained'])
        empty = self.s.apply_rerank('query', self.selection(brief, [], True))
        self.assertEqual(empty['selected_refs'], []); self.assertTrue(empty['abstained'])
        self.s.review('query', order[0].split('@')[0], 1, 'retract')
        result = self.s.apply_rerank('query', self.selection(brief, order[:2]), top_k=2)
        self.assertEqual(result['selected_refs'], order[1:2]); self.assertTrue(result['warnings'])
        fallback = self.s.apply_rerank('query', {'retrieval_id': brief['retrieval_id']})
        self.assertEqual(fallback['selected_refs'], [r for r in self.refs(brief) if r != order[0]])
        self.task('nothing matches', 'empty')
        empty_brief = self.retrieve(task='empty')
        self.assertEqual(self.s.apply_rerank('empty', {'retrieval_id': empty_brief['retrieval_id']})['selected_refs'], [])

    def test_ownership_policy_snapshot_and_mutation_of_returned_candidates(self):
        ref = self.publish('alpha'); foreign = self.publish('alpha foreign', project='other'); self.task()
        brief = self.retrieve(); self.assertNotIn(foreign, self.refs(brief))
        brief['candidates'].append({'entry_ref': foreign, 'title':'forged', 'claim':'forged'})
        with self.assertRaises(KnowledgeError): self.s.apply_rerank('query', self.selection(brief, [foreign]))
        self.task(task='different')
        with self.assertRaises(KnowledgeError): self.s.apply_rerank('different', {'retrieval_id': brief['retrieval_id']})
        with self.assertRaises(KnowledgeError): self.s.apply_rerank('query', {'retrieval_id': brief['retrieval_id']}, role='public')
        self.s.set_task_roles('query', ['developer'])
        with self.assertRaises(KnowledgeError): self.s.apply_rerank('query', {'retrieval_id': brief['retrieval_id']})
        fresh = self.retrieve()
        self.s.db.execute('UPDATE tasks SET snapshot_seq=snapshot_seq+1 WHERE task_id=?', ('query',))
        with self.assertRaises(KnowledgeError): self.s.apply_rerank('query', {'retrieval_id': fresh['retrieval_id']})

    def test_retrieval_revalidates_all_branches_after_slow_provider(self):
        ref = self.publish('alpha'); self.s.index_sync(); self.task()
        fired = []
        def revoke(kind):
            if kind == 'query' and not fired:
                fired.append(True)
                self.s.review('query', ref.split('@')[0], 1, 'retract')
        self.provider.hook = revoke
        brief = self.s.retrieve('query', plan=self.plan(rewrite='slow new query'))
        self.assertNotIn(ref, self.refs(brief))


class StagedCLIContractTests(Fixture):
    def cli(self, *args):
        result = subprocess.run([sys.executable, '-m', 'harness', '--db', str(self.db), *args], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(result.stdout)
    def input(self, name, value):
        path = self.root / name; path.write_text(json.dumps(value)); return str(path)
    def test_staged_start_retrieve_rerank_packet_and_abstain(self):
        ref = self.publish('alpha')
        start = self.cli('workflow','start','--retrieval','staged','--input', self.input('start.json',dict(task_id='query',project_id='p',goal='alpha',roles=['developer'])), '--output',str(self.root/'start'))
        self.assertIn('planner_paths', start)
        self.assertFalse(list((self.root/'start').glob('scout-*.json')))
        out = self.root/'retrieve'
        self.cli('workflow','retrieve','--task','query','--mode','lexical','--candidate-limit','20','--output',str(out))
        brief = json.loads((out/'retrieval.json').read_text())
        self.assertEqual(self.refs(brief), [ref])
        fallback = self.cli('workflow','rerank','--task','query','--fallback','--retrieval-id',brief['retrieval_id'],'--output',str(self.root/'fallback'),'--budget','800','--top-k','2')
        packet = json.loads(Path(fallback['packet_path']).read_text())
        metadata = json.dumps(packet)
        for value in ('retrieval_fallback',brief['retrieval_id'],brief['plan_digest']): self.assertIn(value, metadata)
        self.assertEqual(len(packet['sources']),1)
        abstain = self.cli('workflow','rerank','--task','query','--input',self.input('abstain.json',self.selection(brief,[],True)),'--output',str(self.root/'abstain'),'--top-k','2')
        packet = json.loads(Path(abstain['packet_path']).read_text())
        self.assertEqual(packet['sources'],[])
        self.assertIn('native_rerank',json.dumps(packet))

if __name__ == '__main__': unittest.main()
