import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from command_center.projects import ProjectStore


ROOT = Path(__file__).resolve().parents[1]


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        self.store = ProjectStore(ROOT, self.workspace)

    def test_each_template_round_trips_through_fresh_store(self):
        for kind, template in [('assets', 'factory/demo_spec.json'), ('world', 'world/demo_spec.json'),
                               ('gameplay', 'gameplay/demo_spec.json'), ('cinematic', 'cinematic/sequence.json'),
                               ('multiplayer', None), ('simulation', 'simulation/demo_spec.json'),
                               ('openworld', 'openworld/demo_spec.json'), ('unified', 'unified/demo_spec.json'),
                               ('living', 'living/demo_spec.json'), ('city', 'city/demo_spec.json'),
                               ('vertical', 'vertical/demo_spec.json'), ('advanced', 'advanced/demo_spec.json'),
                               ('frontline', 'frontline/demo_spec.json')]:
            project = self.store.create('My ' + kind, kind)
            self.assertEqual(project['id'], 'my-' + kind)
            self.assertEqual(project['spec'], json.loads((ROOT / template).read_text()) if template else {})
            self.assertEqual(ProjectStore(ROOT, self.workspace).get(project['id']), project)
            self.assertEqual(self.store.save_spec(project['id'], project['spec']), project)
        self.assertEqual(len(self.store.list()), 13)
        self.assertTrue(all('spec' not in item for item in self.store.list()))

    def test_save_validates_before_replacing(self):
        project = self.store.create('Arena', 'gameplay')
        valid = dict(project['spec'], seed=123)
        self.assertEqual(self.store.save_spec('arena', valid)['spec'], valid)
        invalid = dict(valid, enemies=[dict(valid['enemies'][0], position=[0, 0, 4])])
        with self.assertRaises(ValueError):
            self.store.save_spec('arena', invalid)
        self.assertEqual(self.store.get('arena')['spec'], valid)

    def test_all_kinds_reject_invalid_specs(self):
        for kind in ['assets', 'world', 'cinematic', 'multiplayer', 'simulation', 'openworld', 'unified', 'living',
                     'city', 'vertical', 'advanced', 'frontline']:
            project = self.store.create(kind, kind)
            with self.assertRaises(ValueError):
                self.store.save_spec(kind, {'bad': True})
            self.assertEqual(self.store.get(kind), project)

    def test_city_validates_spec_before_replacing(self):
        for kind in ('city', 'vertical', 'advanced', 'frontline'):
            with self.subTest(kind=kind):
                project = self.store.create(kind, kind)
                changed = dict(project['spec'], blocks=8, traffic=0, civilians=0)
                self.assertEqual(self.store.save_spec(kind, changed)['spec'], changed)
                for invalid in (dict(changed, blocks=9), dict(changed, block_size=48.5), dict(changed, traffic=True)):
                    with self.assertRaises(ValueError):
                        self.store.save_spec(kind, invalid)
                self.assertEqual(self.store.get(kind)['spec'], changed)

    def test_reject_names_paths_and_duplicates(self):
        for name in ['', '../escape', 'a/b', '/abs', '.hidden', 'a\nb', 'x' * 81]:
            with self.assertRaises(ValueError):
                self.store.create(name, 'world')
            with self.assertRaises(ValueError):
                self.store.directory(name)
        with self.assertRaises(ValueError):
            self.store.create('test', 'unknown')
        first = self.store.create('Original', 'world')
        with self.assertRaises((ValueError, FileExistsError)):
            self.store.create('original', 'assets')
        self.assertEqual(self.store.get('original'), first)

    def test_sources_and_linked_storage_are_protected(self):
        with self.assertRaises(ValueError):
            ProjectStore(ROOT, ROOT / 'factory')
        linked = self.workspace / 'linked'
        linked.symlink_to(self.workspace / 'projects', target_is_directory=True)
        with self.assertRaises(ValueError):
            ProjectStore(ROOT, linked)

    def test_reject_links(self):
        self.store.create('A', 'assets')
        home = self.store.directory('a')
        (home.parent / 'alias').symlink_to(home)
        with self.assertRaises(ValueError):
            self.store.directory('alias')
        spec = home / 'spec.json'
        spec.unlink()
        target = self.workspace / 'other.json'
        target.write_text('{}')
        spec.symlink_to(target)
        with self.assertRaises(ValueError):
            self.store.get('a')
        with self.assertRaises(ValueError):
            self.store.save_spec('a', json.loads((ROOT / 'factory/demo_spec.json').read_text()))
        self.assertEqual(target.read_text(), '{}')

    def test_concurrent_creation_publishes_one_complete_record(self):
        def create(_):
            try:
                return self.store.create('Shared', 'assets')
            except (FileExistsError, ValueError):
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = [r for r in pool.map(create, range(8)) if r]
        self.assertEqual(records, [self.store.get('shared')])
