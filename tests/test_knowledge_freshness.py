"""R1 post_hoc tests, independent oracle from documented 14-day contract."""
import tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from pathlib import Path
from harness.knowledge import KnowledgeStore
P=None
from harness.knowledge import KnowledgeError
class Provider:
 model_id='post-hoc-unit-vector/v1';dimensions=3
 def embed(self,texts,kind='document'):return [[1,0,0] for _ in texts]
class FreshnessTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=P); self.root=Path(self.temp.name)
  self.s=KnowledgeStore(self.root/'store.sqlite3',embedder=Provider()); self.s.project_root=self.root
  self.t=datetime(2026,11,1,tzinfo=timezone.utc)
  self.time=patch('harness.knowledge.now',side_effect=lambda:self.t.isoformat());self.time.start()
  self.ftime=patch('harness.freshness.now',side_effect=lambda:self.t.isoformat());self.ftime.start()
 def tearDown(self):self.ftime.stop();self.time.stop();self.s.close();self.temp.cleanup()
 def publish(self,name,dependencies=None):
  task='seed-'+name;self.s.begin_task(task,'p','test')
  f=self.root/(name+'.txt');f.write_text(name+' source observation')
  e=self.s.add_evidence(task,str(f))['evidence_id'];self.s.finish_task(task,{'status':'success','evidence_ids':[e]})
  p=dict(title=name,claim=f.read_text(),kind='observation',symbols=[name],evidence_ids=[e],basis={'evidence_id':e,'quote':f.read_text()})
  if dependencies:p['dependencies']=dependencies
  self.s.propose(task,[p],'b');rs=self.s.reconcile()['receipts'];return next(r['entry_refs'][0] for r in rs if r.get('entry_refs'))
 def task(self,name='query'):
  self.s.begin_task(name,'p','test retrieval');self.s.index_sync();return name
 def assert_absent(self,task,ref):
  key=ref.rsplit('@',1)[0]
  for mode in ['lexical','semantic','hybrid']:
   self.assertNotIn(key,[r['entry_id'] for r in self.s.search(task,key,mode=mode)['results']],mode)
  with self.assertRaises(KnowledgeError) as ctx:self.s.get_entry(task,key)
  self.assertEqual(ctx.exception.code,'not_found')
 def test_ttl_boundary_all_modes_and_packet(self):
  ref=self.publish('BoundaryClock');task=self.task();key=ref.split('@')[0]
  packet=self.s.prepare_context(task,selected_refs=[ref])
  self.t+=timedelta(days=14,microseconds=-1)
  for mode in ['lexical','semantic','hybrid']:self.assertEqual(self.s.search(task,'BoundaryClock',mode=mode)['results'][0]['entry_id'],key)
  self.t+=timedelta(microseconds=1);self.assert_absent(task,ref)
  with self.assertRaises(KnowledgeError):self.s.expand(packet['packet_id'],ref)
  self.assertEqual(self.s.export_project('p')['entries'][0]['persisted_state'],'active')
 def test_file_dependency_drift_all_modes(self):
  f=self.root/'config.toml';f.write_text('timeout=1')
  ref=self.publish('SourceDrift',{'files':['config.toml']});task=self.task()
  self.assertTrue(self.s.search(task,'SourceDrift',mode='semantic')['results'])
  f.write_text('timeout=2');self.assert_absent(task,ref)
 def test_dependency_revision_retraction_propagates(self):
  base=self.publish('Upstream');child=self.publish('Downstream',{'entries':[base]});task=self.task()
  self.s.review(task,base.split('@')[0],1,'retract');self.assert_absent(task,child)
 def test_old_snapshot_and_current_revocation_all_modes(self):
  self.s.begin_task('old','p','old snapshot');ref=self.publish('Later');task=self.task()
  self.assert_absent('old',ref)
  self.s.review(task,ref.split('@')[0],1,'retract');self.assert_absent(task,ref)
 def test_delayed_reconcile_does_not_refresh_outcome(self):
  self.s.begin_task('delayed','p','delay');f=self.root/'delayed.txt';f.write_text('Delayed observation')
  e=self.s.add_evidence('delayed',str(f))['evidence_id'];self.s.finish_task('delayed',{'status':'success','evidence_ids':[e]})
  self.t+=timedelta(days=15)
  self.s.propose('delayed',[dict(title='Delayed',claim=f.read_text(),kind='observation',evidence_ids=[e],basis={'evidence_id':e,'quote':f.read_text()})],'b')
  receipts=self.s.reconcile()['receipts'];ref=next(r['entry_refs'][0] for r in receipts if r.get('entry_refs'));task=self.task();self.assert_absent(task,ref)
if __name__=='__main__':unittest.main(verbosity=2)
