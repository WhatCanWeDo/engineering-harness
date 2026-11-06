"""Behavioral checks for the portable helpers. No LLM or network required."""
import copy
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import shlex
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/understand-changes'
sys.path.insert(0, str(SKILL / 'scripts'))
import delivery
spec = importlib.util.spec_from_file_location('renderer', SKILL / 'scripts/render_explainer.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def document():
    return {
        'version': 1, 'title': 'Test explanation', 'scope': 'Synthetic fixture only',
        'sections': [{'id': ident, 'title': ident, 'blocks': [{'type': 'paragraph', 'text': 'Synthetic fixture'}]}
                     for ident in renderer.SECTION_IDS],
        'quiz': [{'id': f'q{i}', 'question': f'Question {i}?', 'concept': f'Concept {i}',
                  'correct_option_id': 'c',
                  'options': [{'id': c, 'text': f'Option {c}', 'explanation': f'Reason {c}'} for c in 'abcd']}
                 for i in range(5)]
    }


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.data_script = False
        self.payload = ''

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'script':
            self.data_script = dict(attrs).get('id') == 'quiz-data'

    def handle_endtag(self, tag):
        if tag == 'script':
            self.data_script = False

    def handle_data(self, data):
        if self.data_script:
            self.payload += data


class RendererTests(unittest.TestCase):
    def test_rejects_invalid_quiz(self):
        mutations = [lambda d: d['quiz'].pop(),
                     lambda d: d['quiz'][0]['options'].pop(),
                     lambda d: d['quiz'][0].update(correct_option_id='missing'),
                     lambda d: d['quiz'][0]['options'][1].update(id='a'),
                     lambda d: d['quiz'][0]['options'][1].update(text='Option a'),
                     lambda d: d['quiz'][1].update(question='Question 0?'),
                     lambda d: d.update(version=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                doc = document()
                mutate(doc)
                with self.assertRaises(ValueError):
                    renderer.validate(doc)

    def test_shuffle_preserves_answers_and_explanations(self):
        doc = document()
        original = copy.deepcopy(doc)
        quiz, record = renderer.prepare(doc)
        self.assertEqual(doc, original)
        for old, new, stat in zip(doc['quiz'], quiz, record['questions']):
            self.assertEqual({o['id']: o for o in old['options']}, {o['id']: o for o in new['options']})
            self.assertEqual(new['options'][stat['position']]['id'], old['correct_option_id'])

    def test_untrusted_text_does_not_create_executable_markup(self):
        doc = document()
        injection = '</script><script>alert(1)</script><img src=x onerror=alert(2)>@@TITLE@@'
        doc['title'] = injection
        doc['sections'][0]['blocks'][0]['text'] = injection
        doc['quiz'][0]['options'][0]['text'] = injection
        quiz, _ = renderer.prepare(doc)
        output = renderer.render(doc, quiz)
        parser = Parser()
        parser.feed(output)
        self.assertEqual(sum(t == 'script' for t, _ in parser.tags), 2)
        self.assertFalse(any(t == 'img' for t, _ in parser.tags))
        parsed = json.loads(parser.payload)
        self.assertTrue(any(o['text'] == injection for o in parsed[0]['options']))

    def test_no_external_dependencies(self):
        doc = document()
        quiz, _ = renderer.prepare(doc)
        parser = Parser()
        parser.feed(renderer.render(doc, quiz))
        for tag, attrs in parser.tags:
            self.assertFalse('src' in attrs or tag in ('link', 'iframe', 'object'))
            self.assertFalse('href' in attrs and not attrs['href'].startswith('#'))

    def test_length_warning_allows_natural_variation(self):
        row = {'quiz_hash': 'x', 'questions': [{'position': 0, 'lengths': [40, 10, 20, 30]} for _ in range(5)]}
        self.assertTrue(any('longest' in w for w in renderer.audit(row, [])))
        row['questions'][0]['lengths'] = [10, 40, 20, 30]
        row['questions'][1]['lengths'] = [10, 40, 20, 30]
        self.assertFalse(any('longest' in w for w in renderer.audit(row, [])))

    def test_history_detects_repeated_length_pattern(self):
        rows = [{'quiz_hash': str(i), 'questions': [{'position': n % 4, 'lengths': [100 if k == n % 4 else 10 for k in range(4)]} for n in range(5)]} for i in range(4)]
        self.assertTrue(any('History:' in w and 'longest' in w for w in renderer.audit(rows[-1], rows[:-1])))

    def test_render_cli_no_overwrite_and_history_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'input.json'
            source.write_text(json.dumps(document()))
            history = folder / 'history.jsonl'
            for name in ('first.html', 'second.html'):
                result = subprocess.run([sys.executable, str(SKILL / 'scripts/render_explainer.py'), str(source), '--output', str(folder / name), '--history', str(history)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(history.read_text().splitlines()), 1)
            original = (folder / 'first.html').read_text()
            again = subprocess.run([sys.executable, str(SKILL / 'scripts/render_explainer.py'), str(source), '--output', str(folder / 'first.html'), '--no-history'], capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((folder / 'first.html').read_text(), original)


    def test_optional_history_write_failure_preserves_successful_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'input.json'
            source.write_text(json.dumps(document()))
            blocker = folder / 'not-a-directory'
            blocker.write_text('leave this file intact')
            output = folder / 'explanation.html'
            result = subprocess.run([sys.executable, str(SKILL / 'scripts/render_explainer.py'), str(source), '--output', str(output), '--history', str(blocker / 'history.jsonl')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['history_recorded'])
            self.assertTrue(any('not recorded' in w for w in report['warnings']))
            self.assertTrue(output.read_text().endswith('</script></body></html>\n'))
            self.assertEqual(blocker.read_text(), 'leave this file intact')


class DeliveryTests(unittest.TestCase):
    def test_link_and_command_preserve_special_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "разбор [a] (b) #1% ' $(echo nope).html"
            path.write_text('<!doctype html><title>Example</title>')
            with mock.patch.object(delivery.webbrowser, 'open') as launcher:
                result = delivery.describe(path)
            launcher.assert_not_called()
            target = result['file_link'].split('](<', 1)[1][:-2]
            self.assertEqual(unquote(target), path.resolve().as_posix())
            if result['command_shell'] == 'posix':
                self.assertEqual(shlex.split(result['open_command']), result['open_argv'])
            self.assertFalse(result['launch_requested'])

    def test_open_sends_file_uri_to_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a #2.html'
            path.write_text('<!doctype html>')
            with mock.patch.dict(delivery.os.environ, {}, clear=True), mock.patch.object(delivery.webbrowser, 'open', return_value=True) as launcher:
                delivery.request_browser(path)
            launcher.assert_called_once_with(path.resolve().as_uri(), new=2)

    def test_browser_rejection_is_an_error_and_does_not_change_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'example.html'
            path.write_text('unchanged')
            with mock.patch.dict(delivery.os.environ, {}, clear=True), mock.patch.object(delivery.webbrowser, 'open', return_value=False):
                with self.assertRaisesRegex(ValueError, 'No browser'):
                    delivery.request_browser(path)
            self.assertEqual(path.read_text(), 'unchanged')

    def test_ssh_does_not_launch_browser_on_wrong_machine(self):
        with mock.patch.dict(delivery.os.environ, {'SSH_CONNECTION': 'test'}), mock.patch.object(delivery.webbrowser, 'open') as launcher:
            with self.assertRaisesRegex(ValueError, 'Remote SSH'):
                delivery.request_browser('irrelevant.html')
            launcher.assert_not_called()

    def test_missing_and_non_html_files_are_not_advertised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing.html'
            with self.assertRaises(FileNotFoundError):
                delivery.describe(path)
            path = Path(tmp) / 'notes.txt'
            path.write_text('text')
            with self.assertRaisesRegex(ValueError, 'HTML'):
                delivery.describe(path)

    def test_default_output_is_persistent_unique_and_immediately_linkable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'input.json'
            source.write_text(json.dumps(document()))
            outputs = []
            for _ in range(2):
                env = dict(delivery.os.environ, HOME=str(folder))
                result = subprocess.run([sys.executable, str(SKILL / 'scripts/render_explainer.py'), str(source), '--no-history'], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                output = Path(report['output'])
                self.assertTrue(output.is_file())
                self.assertTrue(output.is_relative_to(folder.resolve() / '.local/share/engineering-harness/explainers'))
                self.assertEqual(report['delivery']['file_path'], str(output))
                outputs.append(output)
            self.assertNotEqual(*outputs)


class PreferenceTests(unittest.TestCase):
    def call(self, path, *args):
        return subprocess.run([sys.executable, str(SKILL / 'scripts/preferences.py'), '--path', str(path), *args], capture_output=True, text=True)

    def test_task_override_is_not_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            shown = self.call(path, 'show', '--depth', 'deep')
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertEqual(json.loads(shown.stdout)['depth'], 'deep')
            self.assertFalse(path.exists())
            saved = self.call(path, 'set', '--depth', 'brief', '--frequency', 'on_request')
            self.assertEqual(saved.returncode, 0, saved.stderr)
            overridden = json.loads(self.call(path, 'show', '--depth', 'medium').stdout)
            self.assertEqual(overridden['depth'], 'medium')
            self.assertEqual(overridden['frequency'], 'on_request')
            self.assertEqual(json.loads(path.read_text())['depth'], 'brief')
            self.assertEqual(overridden['quiz']['questions'], 5)

    def test_invalid_personal_preference_is_not_silently_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text('{"depth":"unsupported"}')
            result = self.call(path, 'show', '--depth', 'deep')
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
