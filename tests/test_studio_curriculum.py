import unittest

from command_center.dispatch import build_dispatch_plan, default_profile
from command_center.provenance import spec_digest
from command_center.studio_curriculum import curriculum, training_instruction


class CurriculumTests(unittest.TestCase):
    def test_core_disciplines_and_role_coverage_are_versioned(self):
        result = curriculum()
        self.assertEqual(result['version'], 1)
        self.assertEqual(result['curriculum_sha256'], spec_digest({k: v for k, v in result.items()
                                                                if k != 'curriculum_sha256'}))
        ids = {track['id'] for track in result['tracks']}
        self.assertTrue({'game-design', 'game-development', 'modeling', 'textures', 'storytelling'} <= ids)
        roles = {row['id'] for row in default_profile()['roles']}
        self.assertEqual({role for track in result['tracks'] for role in track['roles']}, roles)
        self.assertEqual(len(ids), len(result['tracks']))
        for track in result['tracks']:
            self.assertTrue(set(track['roles']) <= roles)
            for key in ('workflow', 'deliverables', 'verification'):
                self.assertGreaterEqual(len(track[key]), 2)
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in track[key]))
            self.assertTrue(track['exercise'].strip())
        result['tracks'][0]['workflow'].clear()
        self.assertTrue(curriculum()['tracks'][0]['workflow'])

    def test_all_six_agents_receive_role_specific_curriculum_at_dispatch(self):
        profile = default_profile()['roles']
        dispatch = build_dispatch_plan({'id': 'sample', 'name': 'Sample', 'kind': 'world', 'spec': {}},
                                       ('Exercise',) * len(profile))
        for role, item in zip(profile, dispatch['spawn_args'], strict=True):
            instruction = training_instruction(role['id'])
            self.assertIn(instruction, item['message'])
            self.assertIn('applicable', instruction)
            for track in curriculum()['tracks']:
                if role['id'] in track['roles']:
                    self.assertIn(track['title'], instruction)
        with self.assertRaises(ValueError):
            training_instruction('unrecognized')
