"""Post-hoc adversarial MVP2 tests; synthetic providers prove mechanics only.

Run: HARNESS_CANDIDATE_ROOT=/path/to/copy .venv/bin/python -m unittest discover
     -s tests -p test_knowledge_semantic_adversarial.py -v
No downloads, external services, original model-bundle writes or private tests.
"""
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get("HARNESS_CANDIDATE_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT))
from harness.knowledge import KnowledgeStore
from harness import cli, embeddings


class ControlledProvider:
    model_id = 'adversarial-synthetic/v1'
    dimensions = 2

    def __init__(self):
        self.hook = None
        self.vector = [1., 0.]

    def embed(self, texts, kind='document'):
        if self.hook:
            hook, self.hook = self.hook, None
            hook(kind)
        return [self.vector[:] for _ in texts]


class SemanticAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.provider = ControlledProvider()
        self.store = KnowledgeStore(self.home / 'db.sqlite3', embedder=self.provider)
        self.serial = 0

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def publish(self, project='p'):
        self.serial += 1
        task = 'author' + str(self.serial)
        self.store.begin_task(task, project, 'needle')
        file = self.home / (task + '.txt')
        file.write_text('needle observed', encoding='utf-8')
        ev = self.store.add_evidence(task, file)['evidence_id']
        self.store.finish_task(task, {'status': 'success', 'evidence_ids': [ev]})
        self.store.propose(task, [{'title': 'needle', 'claim': 'needle observed',
            'kind': 'observation', 'evidence_ids': [ev], 'basis': {'evidence_id': ev, 'quote': 'needle observed'}}], 'batch')
        receipts = self.store.reconcile()['receipts']
        ref = next(r['entry_refs'][0] for r in receipts if r['entry_refs'])
        return ref.rsplit('@', 1)[0]

    def test_missing_provider_empty_visible_corpus_explicitly_degrades(self):
        """MVP2 search: absence of provider must report lexical/degraded."""
        self.store.begin_task('reader', 'p', 'needle')
        self.store.embedder = None
        for mode in ('semantic', 'hybrid'):
            with self.subTest(mode=mode):
                result = self.store.search('reader', 'needle', mode=mode)
                self.assertEqual((result['mode'], result['status']), ('lexical', 'degraded'))
                self.assertTrue(result['warnings'])
                self.assertEqual(result['results'], [])

    def test_subnormal_nonzero_vectors_are_normalized_before_storage(self):
        """MVP2 index: finite nonzero vectors are persisted normalized."""
        self.publish()
        self.provider.vector = [5e-324, 5e-324]
        self.store.index_sync()
        vector = json.loads(self.store.db.execute('SELECT vector FROM embedding_vectors').fetchone()[0])
        self.assertAlmostEqual(math.hypot(*vector), 1., places=12)

    def test_cli_malformed_bundle_root_has_no_traceback(self):
        """MVP2 CLI: unavailable local provider must have a handled fallback."""
        self.publish()
        self.store.begin_task('reader', 'p', 'needle')
        bundle = self.home / 'bundle'
        bundle.mkdir()
        (bundle / 'manifest.json').write_text('[]', encoding='utf-8')
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            try:
                code = cli.main(['--db', str(self.store.path), '--semantic-model', str(bundle),
                             'knowledge', 'search', '--task', 'reader', '--query', 'needle', '--mode', 'semantic'])
            except AttributeError as exc:
                self.fail('CLI leaks unhandled bundle error: ' + str(exc))
        self.assertEqual(code, 0, error.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual((result['mode'], result['status']), ('lexical', 'degraded'))

    def test_bundle_unhashed_runtime_config_cannot_reuse_identity(self):
        """MVP2 bundle identity: runtime config changes must invalidate identity.

        Tiny synthetic bundle; runtime-version lookup stubbed, no model executed.
        tokenizer_config.json is a FastEmbed runtime input (truncation policy).
        """
        bundle = self.home / 'bundle'
        files = bundle / 'files'
        files.mkdir(parents=True)
        hashes = {}
        for name in ('tokenizer.json', 'model_optimized.onnx'):
            data = b'synthetic fixture, not executable model'
            (files / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        config = files / 'tokenizer_config.json'
        config.write_text('{"model_max_length":128}')
        manifest = {'version': 1, 'model': embeddings.MODEL, 'dimensions': 384,
                    'policy': embeddings.POLICY, 'fastembed_version': 'stub',
                    'onnxruntime_version': 'stub', 'repository': 'fixture',
                    'revision': 'fixture-v1', 'files': hashes}
        (bundle / 'manifest.json').write_text(json.dumps(manifest))
        with patch.object(embeddings, 'version', return_value='stub'):
            try:
                first = embeddings.LocalEmbedder(bundle)
            except ValueError:
                return  # Rejecting the incomplete manifest is also correct.
            config.write_text('{"model_max_length":16}')
            try:
                second = embeddings.LocalEmbedder(bundle)
            except ValueError:
                return
        self.assertNotEqual(first.model_id, second.model_id,
                            'Unhashed runtime config is accepted with unchanged index identity')

    def test_query_delay_cannot_revive_retracted_entry(self):
        entry = self.publish()
        self.store.index_sync()
        self.store.begin_task('reader', 'p', 'needle')
        self.provider.hook = lambda kind: self.store.review('reader', entry, 1, 'retract')
        result = self.store.search('reader', 'needle', mode='semantic')
        self.assertEqual(result['results'], [])

    def test_index_delay_does_not_attach_old_vector_to_new_revision(self):
        entry = self.publish()
        self.store.begin_task('admin', 'p', 'needle')
        self.provider.hook = lambda kind: self.store.review('admin', entry, 1, 'approve', claim='changed claim')
        result = self.store.index_sync()
        self.assertEqual(result['indexed'], 0)
        self.assertEqual(result['remaining'], 1)
        self.assertEqual(self.store.index_sync()['indexed'], 1)


if __name__ == '__main__':
    unittest.main()
