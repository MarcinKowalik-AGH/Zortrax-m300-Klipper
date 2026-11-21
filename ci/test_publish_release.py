# Marcin Kowalik <mkowalik@agh.edu.pl>
# test_publish_release.py - Sprawdza publikację finalną i RC oraz blokady niezweryfikowanych wydań.
"""Exercise the actual publication script with local GitHub responses and assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 40
RUN = '12345'
REPO = 'example/m300'

GH = '''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
a = sys.argv[1:]
log = pathlib.Path(os.environ['M300_PUBLISH_TEST_LOG'])
with log.open('a') as f: f.write(json.dumps(a) + '\\n')
if a[:2] == ['release', 'view']:
    if '--json' in a: print('Previous release notes')
    else: sys.exit(0 if os.environ.get('M300_PUBLISH_TEST_EXISTS') else 1)
elif a[0] == 'api':
    if '/actions/runs/' in a[1]:
        print(json.dumps(dict(head_sha=os.environ['SOURCE_SHA'], head_branch='main',
            head_repository=dict(full_name=os.environ['GITHUB_REPOSITORY']),
            path='.github/workflows/build-m300.yml', status='completed',
            conclusion=os.environ.get('M300_PUBLISH_TEST_CONCLUSION', 'success'))))
    else:
        print(os.environ.get('M300_PUBLISH_TEST_TAG_SHA', ''))
elif a[:2] == ['run', 'download']:
    shutil.copytree(os.environ['M300_PUBLISH_TEST_ASSETS'], a[a.index('--dir') + 1])
elif a[:2] not in (['release', 'create'], ['release', 'edit']):
    sys.exit('Unexpected GitHub operation: ' + repr(a))
'''


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        for name, text in (('gh', GH), ('git', '#!/bin/sh\nprintf "%s\\n" "$SOURCE_SHA"\n')):
            p = self.bin / name
            p.write_text(text)
            p.chmod(0o755)
        self.assets = self.root / 'assets'
        self.assets.mkdir()

    def publish(self, tag, **overrides):
        (self.root / 'PORT.json').write_text(json.dumps(dict(
            distribution_version=tag, supersedes_version='v1.0.0-rc.34')))
        notes = self.root / 'docs/en' / ('RELEASE_' + tag + '.md')
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text('Verified release notes\n')
        files = {
            'BUILD_PROVENANCE.json': json.dumps(dict(github_commit=SHA, github_run_id=RUN,
                distribution_version=tag, model='M300_CLASSIC', release_stage='VERIFIED')),
            'install-fresh.py': '# fixture\n', 'KLIPPER_HOST/klippy/klippy.py': '# fixture\n',
            'MCU/M300APP.M3B': 'fixture bytes', 'FIRST_INSTALL_PL.md': 'Install PL\n',
            'FIRST_INSTALL_EN.md': 'Install EN\n',
        }
        for name, text in files.items():
            p = self.assets / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        sums = ''.join(hashlib.sha256((self.assets / name).read_bytes()).hexdigest()
                       + '  ' + name + '\n' for name in files)
        (self.assets / 'SHA256SUMS').write_text(sums)
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                   SOURCE_SHA=SHA, SOURCE_RUN=RUN, GITHUB_REPOSITORY=REPO,
                   RUNNER_TEMP=str(self.root), M300_PUBLISH_TEST_LOG=str(self.log),
                   M300_PUBLISH_TEST_ASSETS=str(self.assets), **overrides)
        result = subprocess.run(['bash', str(ROOT / 'ci/publish_release.sh')],
                                cwd=self.root, env=env, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_final_release_is_latest_and_uses_the_verified_commit(self):
        result, calls = self.publish('v1.0.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        create = next(c for c in calls if c[:2] == ['release', 'create'])
        self.assertIn('--latest', create)
        self.assertNotIn('--prerelease', create)
        self.assertEqual(create[create.index('--target') + 1], SHA)
        self.assertTrue(any(c[:2] == ['release', 'edit'] for c in calls))

    def test_rc_remains_a_prerelease(self):
        result, calls = self.publish('v1.0.1-rc.1')
        self.assertEqual(result.returncode, 0, result.stderr)
        create = next(c for c in calls if c[:2] == ['release', 'create'])
        self.assertIn('--prerelease', create)
        self.assertNotIn('--latest', create)

    def test_existing_release_is_immutable(self):
        result, calls = self.publish('v1.0.0', M300_PUBLISH_TEST_EXISTS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)

    def test_failed_build_cannot_publish(self):
        result, calls = self.publish('v1.0.0', M300_PUBLISH_TEST_CONCLUSION='failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[:2] == ['release', 'create'] for c in calls))

    def test_an_existing_tag_on_another_commit_cannot_move(self):
        result, calls = self.publish('v1.0.0', M300_PUBLISH_TEST_TAG_SHA='b' * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing to move', result.stderr)
        self.assertFalse(any(c[:2] == ['release', 'create'] for c in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
