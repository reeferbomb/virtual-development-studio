import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from command_center import admin_lineage as lineage


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.space = tempfile.TemporaryDirectory()
        self.addCleanup(self.space.cleanup)
        self.area = Path(self.space.name)
        self.repo = self.area / 'checkout'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.file = self.repo / 'scene'
        self.file.write_bytes(b'opening\n')
        self.git('add', 'scene')
        self.git('commit', '-qm', 'opening')
        self.opening = self.git('rev-parse', 'HEAD')

    def git(self, *args, cwd=None):
        result = subprocess.run([shutil.which('git', path=os.defpath), '-c', 'user.name=Fixture',
                                 '-c', 'user.email=fixture@invalid', '-c', 'core.hooksPath=/dev/null',
                                 '-c', 'commit.gpgSign=false', *args],
                                cwd=cwd or self.repo, check=True, capture_output=True,
                                env={'PATH': os.defpath, 'HOME': str(self.area), 'GIT_CONFIG_NOSYSTEM': '1',
                                     'GIT_CONFIG_GLOBAL': '/dev/null'})
        return result.stdout.decode().strip()

    def capture(self, path=None, project='glass-yard', version='v41'):
        return lineage.capture_git(path or self.repo, project, version)

    def test_content_and_index_identify_dirty_tree_without_writing_git_index(self):
        index = self.repo / '.git' / 'index'
        original = (index.read_bytes(), index.stat().st_mtime_ns)
        clean = self.capture()
        self.assertFalse(clean['dirty'])
        self.assertEqual(clean, self.capture())
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), original)
        self.file.write_bytes(b'other\n')
        modified = self.capture()
        self.assertTrue(modified['dirty'])
        self.assertEqual(modified['worktree_count'], 1)
        self.assertNotEqual(clean['sha256'], modified['sha256'])
        self.git('add', 'scene')
        self.file.write_bytes(b'opening\n')
        staged = self.capture()
        self.assertEqual(staged['sha256'], clean['sha256'])
        self.assertNotEqual(staged['index_sha256'], clean['index_sha256'])
        self.assertEqual((staged['staged_count'], staged['worktree_count']), (1, 1))
        report = lineage.compare_sources(clean, staged, 'same')
        self.assertTrue(report['quarantine'])
        self.assertTrue(report['same_content'])
        self.assertEqual(report['ancestry'], 'same')
        self.file.unlink()
        self.assertEqual(self.capture()['file_count'], 0)

    def test_literal_worktree_excludes_ignored_files_and_hashes_link_text(self):
        self.git('config', 'core.excludesFile', str(self.area / 'excludes'))
        (self.area / 'excludes').write_text('scratch.log\n')
        (self.repo / 'scratch.log').write_bytes(b'ignored')
        outside = self.area / 'outside'
        outside.write_text('external')
        link = self.repo / 'pointer'
        link.symlink_to(outside)
        one = self.capture()
        self.assertEqual((one['file_count'], one['untracked_count']), (2, 1))
        outside.write_text('changed target bytes')
        self.assertEqual(one, self.capture())
        link.unlink()
        link.symlink_to('different-target')
        self.assertNotEqual(one['sha256'], self.capture()['sha256'])
        self.file.chmod(0o755)
        self.assertEqual(self.capture()['worktree_count'], 1)

    def test_symlink_parent_never_imports_an_external_file(self):
        folder = self.repo / 'art'
        folder.mkdir()
        (folder / 'pane').write_text('tracked')
        self.git('add', 'art')
        self.git('commit', '-qm', 'panes')
        outside = self.area / 'offsite'
        folder.rename(outside)
        folder.symlink_to(outside, target_is_directory=True)
        first = self.capture()
        (outside / 'pane').write_text('different')
        self.assertEqual(first, self.capture())
        self.assertEqual((first['worktree_count'], first['untracked_count']), (1, 1))

    def test_archive_collision_and_namespaces_preserve_candidates(self):
        alpha, beta = self.area / 'candidate.mp4', self.area / 'unverified.tar'
        alpha.write_bytes(b'opaque media')
        beta.write_bytes(b'unsupported archive')
        a = lineage.fingerprint_archive(alpha, 'glass-yard', 'v41')
        b = lineage.fingerprint_archive(beta, 'glass-yard', 'v41')
        self.assertEqual(a['sha256'], hashlib.sha256(alpha.read_bytes()).hexdigest())
        report = lineage.compare_sources(a, b)
        self.assertTrue(report['quarantine'])
        self.assertFalse(report['same_content'])
        self.assertEqual(report['ancestry'], 'unknown')
        self.assertEqual((alpha.read_bytes(), beta.read_bytes()), (b'opaque media', b'unsupported archive'))
        mixed = lineage.compare_sources(self.capture(), a)
        self.assertIsNone(mixed['same_content'])
        self.assertTrue(mixed['quarantine'])
        beta.write_bytes(alpha.read_bytes())
        duplicate = lineage.fingerprint_archive(beta, 'glass-yard', 'v41')
        self.assertFalse(lineage.compare_sources(a, duplicate)['quarantine'])
        other_project = lineage.fingerprint_archive(beta, 'slate-yard', 'v41')
        self.assertFalse(lineage.compare_sources(a, other_project)['same_project_tag'])
        self.assertEqual(other_project['tag'], 'project/slate-yard/v41')

    def test_local_commit_ancestry_in_both_directions_and_on_separate_branches(self):
        relate = lambda a, b: lineage.git_ancestry(self.repo, a, b)
        self.assertEqual(relate(self.opening, self.opening), 'same')
        self.file.write_text('forward')
        self.git('commit', '-qam', 'forward')
        forward = self.git('rev-parse', 'HEAD')
        base = self.capture()
        self.assertEqual(relate(self.opening, forward), 'ahead')
        self.assertEqual(relate(forward, self.opening), 'behind')
        self.git('switch', '-qc', 'alternate', self.opening)
        self.file.write_text('alternate')
        self.git('commit', '-qam', 'alternate')
        alternate = self.git('rev-parse', 'HEAD')
        self.assertEqual(relate(forward, alternate), 'diverged')
        other = self.capture(version='v42')
        for relation in ['unknown', 'diverged']:
            report = lineage.compare_sources(base, other, relation)
            self.assertTrue(report['quarantine'])
            self.assertFalse(report['tag_collision'])
        independent = self.capture(project='slate-yard', version='v42')
        self.assertFalse(lineage.compare_sources(base, independent, 'diverged')['quarantine'])
        for unknown in [None, 'v41', '0' * 40, self.git('rev-parse', 'HEAD^{tree}')]:
            self.assertEqual(relate(alternate, unknown), 'unknown')
        (self.repo / '.git' / 'shallow').write_text(forward + '\n')
        self.assertEqual(relate(forward, alternate), 'unknown')

    def test_clean_canonical_identity_is_required_for_a_shared_release(self):
        canonical = self.capture()
        copy = self.area / 'copy'
        self.git('clone', '--quiet', '--no-local', str(self.repo), str(copy))
        candidate = self.capture(copy)
        self.assertTrue(lineage.release_eligibility(canonical, canonical)['eligible'])
        self.assertFalse(lineage.release_eligibility(canonical, candidate, 'same')['eligible'])
        (copy / 'scene').write_text('candidate')
        dirty = self.capture(copy)
        self.assertTrue(lineage.compare_sources(canonical, dirty)['quarantine'])
        self.assertFalse(lineage.release_eligibility(dirty, dirty)['eligible'])
        self.assertFalse(lineage.release_eligibility(canonical, self.capture(version='v42'))['eligible'])
        self.assertFalse(lineage.release_eligibility(canonical, self.capture(project='another'))['eligible'])

    def test_local_filters_and_fsmonitor_are_never_run(self):
        script = self.area / 'marker-script'
        marker = self.area / 'marker'
        script.write_text(f'#!/bin/sh\ntouch "{marker}"\ncat\n')
        script.chmod(0o755)
        self.git('config', 'filter.probe.clean', str(script))
        self.git('config', 'core.fsmonitor', str(script))
        (self.repo / '.gitattributes').write_text('scene filter=probe\n')
        self.file.write_bytes(b'updated')
        self.assertTrue(self.capture()['dirty'])
        self.assertFalse(marker.exists())

    def test_input_validation_bounds_and_triage(self):
        self.assertEqual(lineage.triage_proposal('content', 'local review', 'deferred'),
                         {'owner': 'content', 'source': 'local review', 'status': 'deferred'})
        for args in [('', 'source'), ('owner', ''), ('owner', 'source', 'published')]:
            with self.assertRaises(ValueError):
                lineage.triage_proposal(*args)
        for project, version in [('foo/bar', 'v1'), ('good', '../v5'), ('good', 'v1..2')]:
            with self.assertRaises(ValueError):
                lineage.project_tag(project, version)
        with self.assertRaises(ValueError):
            lineage.capture_git(self.area, 'yard', 'v1')
        with patch.object(lineage, '_MAX_BYTES', 1), self.assertRaises(ValueError):
            self.capture()
        with patch.object(lineage, '_MAX_BYTES', 1), self.assertRaises(ValueError):
            lineage.fingerprint_archive(self.file, 'yard', 'v1')
        with patch.object(lineage, '_MAX_OUTPUT', 1), self.assertRaises(ValueError):
            self.capture()
        clean = self.capture()
        with self.assertRaises(ValueError):
            lineage.compare_sources(clean, clean, 'ahead')
        with self.assertRaises(ValueError):
            lineage.compare_sources(clean, dict(clean, sha256='invalid'))


if __name__ == '__main__':
    unittest.main()
