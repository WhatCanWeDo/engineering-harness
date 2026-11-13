"""Post-hoc adversarial regression checks; independent public-contract assertions.
Run with managed Python; HARNESS_CANDIDATE optionally selects a frozen disposable tree.
All databases are synthetic and temporary, alongside this test module.
"""
import builtins
import importlib
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get('HARNESS_CANDIDATE', str(HERE.parent)))
from harness.knowledge import KnowledgeStore, KnowledgeError, encode, now
from harness import semantic, workflow

class Provider:
    model_id = 'adversarial-synthetic-v1'
    dimensions = 2
    def __init__(self): self.callback = None; self.calls = []
    def embed(self, texts, kind):
        self.calls.append((list(texts), kind))
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        return [[1.0, 0.0] for _ in texts]

class RetrievalAdversarial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE)
        self.provider = Provider()
        self.store = KnowledgeStore(Path(self.tmp.name) / 'test.db', embedder=self.provider)
        for name in ['A', 'B', 'C']:
            self.store._append(dict(entry_id=name, title='needle '+name, claim='needle evidence '+name,
                kind='observation', scope='project', project_id='p', state='active',
                trust_basis='human_review', evidence_ids=[], applicability={}, tags=[], symbols=[], observed_at=now()))
        self.store.begin_task('T', 'p', 'needle')
        self.store.index_sync()
        self.key = semantic.identity(self.provider)[0]
        self.write_vector('A', '[1,0]'); self.write_vector('B', '[0,1]'); self.write_vector('C', '[-1,0]')
    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def write_vector(self, key, raw, connection=None):
        (connection or self.store.db).execute('UPDATE embedding_vectors SET vector=? WHERE entry_id=?', (raw,key))
    def search(self, query='needle'):
        return self.store.search('T', query, mode='semantic')
    def ids(self, result): return [r['entry_id'] for r in result['results']]
    def plan(self, **extra):
        return dict(version=1, task_id='T', role='developer', original='needle', **extra)
    def mutate_record(self, key, **extra):
        record = self.store._current(key); record.update(extra); record.pop('seq',None)
        self.store.db.execute('UPDATE revisions SET payload=? WHERE entry_id=? AND revision=1', (encode(record),key))
    def test_R1_cache_state_sequence(self):
        self.assertEqual(self.ids(self.search()), ['A','B','C'])
        other = sqlite3.connect(self.store.path, isolation_level=None)
        try:
            self.write_vector('C', '[1,0]', other); self.write_vector('A', '[-1,0]', other)
            self.assertEqual(self.ids(self.search()), ['C','B','A'])
            self.store.db.execute('BEGIN'); self.write_vector('B', '[1,0]')
            self.assertEqual(self.ids(self.search()), ['B','C','A'])
            self.store.db.execute('ROLLBACK')
            self.assertEqual(self.ids(self.search()), ['C','B','A'])
            self.mutate_record('C', state='retracted')
            self.assertEqual(self.ids(self.search()), ['B','A'])
            other.execute("DELETE FROM embedding_vectors WHERE entry_id='B'")
            r=self.search(); self.assertEqual((r['status'], r['mode']), ('degraded','lexical'))
        finally: other.close()
    def test_R1_allowed_json_vectors_require_array(self):
        for raw in ['"10"', '{"1":0,"0":1}']:
            with self.subTest(raw=raw):
                self.write_vector('A', raw)
                result = self.search()
                self.assertEqual((result['status'],result['mode']), ('degraded','lexical'), result)
    def test_R1_malformed_and_extreme_vectors(self):
        for raw in ['null', 'true', '[]', '[0,0]', '[1]', '[1,2,3]', '[NaN,0]', '[Infinity,0]', 'nonsense']:
            with self.subTest(raw=raw):
                self.write_vector('A', raw)
                self.assertEqual(self.search()['status'], 'degraded')
        for raw in ['[1e308,1e308]', '[5e-324,5e-324]', '[1e-308,1e308]']:
            with self.subTest(raw=raw):
                self.write_vector('A', raw)
                self.assertEqual(self.search()['status'], 'ok')
    def test_R1_foreign_malformed_vector_not_poison(self):
        self.mutate_record('C', project_id='foreign')
        self.write_vector('C', 'nonsense')
        result = self.search()
        self.assertEqual(result['status'],'ok'); self.assertEqual(self.ids(result), ['A','B'])
    def test_R1_allowed_membership_and_model_changes(self):
        self.search(); self.mutate_record('A', applicability={'runtime':'other'})
        self.assertEqual(self.ids(self.search()), ['B','C'])
        self.mutate_record('A', applicability={})
        self.assertEqual(self.ids(self.search()), ['A','B','C'])
        self.provider.model_id = 'new-model'
        self.assertEqual(self.search()['status'], 'degraded')
    def test_R1_stdlib_fallback_and_fsum_ties(self):
        self.provider.dimensions = 32
        self.store.db.execute('DELETE FROM embedding_vectors')
        key = semantic.identity(self.provider)[0]
        rng=random.Random(98271)
        for case in range(30):
            q=[rng.uniform(-1,1) for _ in range(32)]
            a=[rng.uniform(-1,1) for _ in range(32)]
            b=a.copy(); b[case%32] += 1e-15
            vals={'A':a,'B':b,'C':[-v for v in a]}
            for name,v in vals.items():
                record=self.store._current(name)
                self.store.db.execute('INSERT OR REPLACE INTO embedding_vectors VALUES(?,?,?,?,?)',
                    (key,name,1,semantic.sha(semantic.document(record)),json.dumps(v)))
            query='case '+str(case)
            self.store.db.execute('INSERT OR REPLACE INTO query_vectors VALUES(?,?,?,?)', (key,'p',semantic.sha(query),json.dumps(q)))
            # Independent math definition used by baseline: max scaling, hypot, fsum.
            def norm(v):
                z=[x/max(map(abs,v)) for x in v]; n=math.hypot(*z); return [x/n for x in z]
            expected=sorted(vals,key=lambda k:(-math.fsum(x*y for x,y in zip(norm(q),norm(vals[k]))),k))
            self.assertEqual(self.ids(self.search(query)),expected)
            self.store._semantic_cache=None
            imp=builtins.__import__
            def blocked(name,*args,**kw):
                if name=='numpy': raise ImportError('Intentional optional dependency absence')
                return imp(name,*args,**kw)
            with patch('builtins.__import__',blocked): self.assertEqual(self.ids(self.search(query)),expected)
    def test_R1_R3_revocation_during_provider(self):
        self.provider.callback=lambda:self.mutate_record('A',state='retracted')
        r=self.store.retrieve('T',self.plan(), mode='semantic')
        self.assertNotIn('A@1',[c['entry_ref'] for c in r['candidates']])
    def test_R3_plan_validation(self):
        bad=[{'version':True},{'version':1.0},{'task_id':'foreign'},{'role':'public'},
             {'original':'needle '},{'unknown':1},{'rewrite':''},{'rewrite':' '},
             {'rewrite':'a'*1001},{'subqueries':['x']*4},{'subqueries':[' ']},
             {'subqueries':None},{'reason':0},{'hypothetical_document':'x'*1501}]
        for extra in bad:
            with self.subTest(extra=extra):
                p=self.plan();p.update(extra)
                with self.assertRaises(KnowledgeError): self.store.retrieve('T',p,mode='lexical',experimental=True)
        for extra in [{'subqueries':['a']},{'hypothetical_document':'a'}]:
            with self.assertRaises(KnowledgeError): self.store.retrieve('T',self.plan(**extra),mode='lexical')
    def test_R3_exact_original_and_dedup_hyde_namespace(self):
        self.store.begin_task('EXACT','p','C')
        p=dict(version=1,task_id='EXACT',role='developer',original='C',rewrite='needle',subqueries=['needle','C'],hypothetical_document='C')
        r=self.store.retrieve('EXACT',p,experimental=True)
        self.assertEqual(r['candidates'][0]['entry_ref'],'C@1')
        self.assertEqual([b['branch'] for b in r['trace']],['original','rewrite','hyde'])
        self.assertTrue(any(t==['C'] and kind=='document' for t,kind in self.provider.calls))
        self.assertTrue(any(t==['C'] and kind=='query' for t,kind in self.provider.calls))
    def test_R3_rerank_validation_binding_staleness_and_fallback(self):
        r=self.store.retrieve('T',self.plan()); rid=r['retrieval_id']
        bad=[{}, {'ranked_refs':['A@1','A@1'],'abstain':False}, {'ranked_refs':['F@1'],'abstain':False},
             {'ranked_refs':['A@1'],'abstain':True}, {'ranked_refs':[],'abstain':False},
             {'ranked_refs':['A@1'],'abstain':1}, {'ranked_refs':['A@1'],'abstain':False,'candidates':[]}]
        for d in bad[1:]:
            with self.subTest(selection=d):
                with self.assertRaises(KnowledgeError):self.store.apply_rerank('T',dict(retrieval_id=rid,**d))
        self.mutate_record('A',state='retracted')
        rr=self.store.apply_rerank('T',dict(retrieval_id=rid,ranked_refs=['A@1','C@1','B@1'],abstain=False),top_k=1)
        self.assertEqual(rr['selected_refs'],['C@1']); self.assertTrue(rr['warnings'])
        rr=self.store.apply_rerank('T',dict(retrieval_id=rid),top_k=1)
        self.assertEqual(rr['selected_refs'],['B@1']); self.assertEqual(rr['mode'],'retrieval_fallback'); self.assertFalse(rr['abstained'])
        self.store.set_task_roles('T',['developer'])
        with self.assertRaises(KnowledgeError):self.store.apply_rerank('T',dict(retrieval_id=rid))
    def test_R4_R5_abstain_packet_and_reranker_brief(self):
        out=Path(self.tmp.name)/'retrieval'
        meta=workflow.retrieve(self.store,'T','developer',self.plan(rewrite='other'),out)
        brief=json.loads(Path(meta['reranker_path']).read_text())
        self.assertNotIn('plan',brief);self.assertNotIn('trace',brief)
        result=workflow.rerank(self.store,'T','developer',dict(retrieval_id=meta['retrieval_id'],ranked_refs=[],abstain=True),Path(self.tmp.name)/'packets')
        packet=json.loads(Path(result['packet_path']).read_text())
        self.assertEqual(packet['sources'],[]);self.assertEqual(packet['text'],'')
        self.assertEqual(packet['mode'],'native_rerank');self.assertTrue(packet['retrieval']['abstained'])

if __name__=='__main__': unittest.main(verbosity=2)
