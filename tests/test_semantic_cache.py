"""R1 cache behavior; oracle is independently computed stable cosine order."""
import builtins
import json
import math
import sqlite3
from unittest.mock import patch
from test_retrieval_staged import Fixture


class SemanticCacheContractTests(Fixture):
    def setUp(self):
        super().setUp()
        self.a = self.publish('alpha')
        self.b = self.publish('beta')
        self.task(goal='unmatched')
        self.s.index_sync()
    def vector(self, ref, vector, connection=None):
        (connection or self.s.db).execute('UPDATE embedding_vectors SET vector=? WHERE entry_id=?', (json.dumps(vector), ref.split('@')[0]))
    def result(self, query='unmatched', mode='semantic'):
        return self.s.search('query', query, mode=mode)
    def ids(self, result):
        return [r['entry_id']+'@'+str(r['revision']) for r in result['results']]
    def assert_order(self, expected):
        for _ in range(2):
            result = self.result()
            self.assertEqual(result['mode'],'semantic'); self.assertEqual(result['status'],'ok')
            self.assertEqual(self.ids(result),expected)
    def test_direct_changes_other_connection_delete_rollback_and_metadata(self):
        self.vector(self.a,[1,0,0]); self.vector(self.b,[0,1,0]); self.assert_order([self.a,self.b])
        with sqlite3.connect(self.db) as other:
            self.vector(self.a,[-1,0,0],other)
        self.assert_order([self.b,self.a])
        self.s.db.execute('BEGIN')
        self.vector(self.a,[1,0,0]); self.assert_order([self.a,self.b])
        self.s.db.execute('ROLLBACK'); self.assert_order([self.b,self.a])
        for field,value in (('revision',99),('content_hash','bad'),('model_key','different')):
            original = self.s.db.execute('SELECT * FROM embedding_vectors WHERE entry_id=?',(self.a.split('@')[0],)).fetchone()
            self.s.db.execute(f'UPDATE embedding_vectors SET {field}=? WHERE entry_id=?',(value,self.a.split('@')[0]))
            result = self.result('alpha')
            self.assertEqual(result['status'],'degraded'); self.assertEqual(result['mode'],'lexical')
            self.s.db.execute('DELETE FROM embedding_vectors WHERE entry_id=?',(self.a.split('@')[0],))
            self.s.db.execute('INSERT INTO embedding_vectors VALUES(?,?,?,?,?)',tuple(original))
            self.assert_order([self.b,self.a])
        self.s.db.execute('DELETE FROM embedding_vectors WHERE entry_id=?',(self.a.split('@')[0],))
        self.assertEqual(self.result('alpha')['status'],'degraded')
    def test_invalid_allowed_foreign_vectors_and_extreme_finite_values(self):
        foreign = self.publish('foreign',project='foreign')
        self.s.index_sync()
        self.vector(foreign,[float('nan'),0,0])
        self.assertEqual(self.result()['mode'],'semantic')
        for vector in ([0,0,0],[float('nan'),0,0],[float('inf'),0,0],[1,0],None,{},['bad',0,0]):
            with self.subTest(vector=vector):
                self.vector(self.a,vector)
                result=self.result('alpha')
                self.assertEqual(result['status'],'degraded'); self.assertEqual(result['mode'],'lexical')
                self.assertTrue(result['warnings'])
        self.vector(self.a,[1e308,1e308,0]); self.vector(self.b,[5e-324,0,0]); self.assert_order([self.b,self.a])
        self.vector(self.a,[5e-324,0,0]); self.assert_order(sorted([self.a,self.b]))
    def test_fsum_near_ties_and_numpy_optional(self):
        q=[1,1e-8,1e-16]
        # Perturbations lie close enough that reduction order can change a tie.
        vectors=[[1,1e-8,0],[1,1.00000001e-8,1e-16]]
        def norm(v):
            scale=max(map(abs,v)); x=[a/scale for a in v]; size=math.hypot(*x); return [a/size for a in x]
        nq=norm(q)
        expected=sorted([self.a,self.b],key=lambda ref:(-math.fsum(a*b for a,b in zip(nq,norm(vectors[[self.a,self.b].index(ref)]))),ref))
        self.vector(self.a,vectors[0]); self.vector(self.b,vectors[1])
        self.provider.embed=lambda texts,kind='document':[q for _ in texts]
        self.assert_order(expected)
        original_import=builtins.__import__
        def optional(name,*args,**kwargs):
            if name=='numpy' or name.startswith('numpy.'): raise ImportError('public optional dependency test')
            return original_import(name,*args,**kwargs)
        self.s.close()
        with patch('builtins.__import__',side_effect=optional):
            from harness.knowledge import KnowledgeStore
            self.s=KnowledgeStore(self.db,embedder=self.provider)
            self.assert_order(expected)
    def test_allowed_membership_changes_and_query_cache_change(self):
        self.vector(self.a,[1,0,0]); self.vector(self.b,[0,1,0]); self.assert_order([self.a,self.b])
        self.s.db.execute('UPDATE query_vectors SET vector=?',(json.dumps([0,1,0]),))
        self.assert_order([self.b,self.a])
        self.s.review('query',self.b.split('@')[0],1,'retract')
        self.assert_order([self.a])
        later=self.publish('later'); self.s.index_sync()
        self.assert_order([self.a]); self.assertNotIn(later,self.ids(self.result()))
    def test_warm_cache_revocation_during_provider_call(self):
        self.result()
        def revoke(kind):
            if kind=='query':
                self.s.review('query',self.a.split('@')[0],1,'retract')
        self.provider.hook=revoke
        result=self.result('new uncached query')
        self.assertEqual(self.ids(result),[self.b])
