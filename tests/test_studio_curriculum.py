import unittest
from pathlib import Path

from command_center.dispatch import build_dispatch_plan, default_profile
from command_center.provenance import spec_digest
from command_center.studio_curriculum import curriculum, training_instruction


class CurriculumTests(unittest.TestCase):
    def test_reference_syllabus_covers_requested_games_and_production_guides(self):
        root = Path(__file__).resolve().parents[1] / 'command_center'
        guide = (root / 'REFERENCE_GAME_ACADEMY.md').read_text(encoding='utf-8')
        for title in ('Mass Effect', 'Mass Effect 2', 'Mass Effect 3', 'The Darkness',
                      'Soul Reaver', 'Call of Duty', 'Battlefield', 'Naughty Bear',
                      'Grand Theft Auto', 'Shenmue', "Majora's Mask", 'Super Mario',
                      'Sonic', 'Ocarina of Time', 'From Dust', 'Civilization Revolution'):
            self.assertIn(title, guide)
        for file in ('NARRATIVE.md', 'COMBAT.md', 'WORLDS.md', 'TRAVERSAL.md',
                     'STRATEGY.md', 'HUD_UI.md'):
            self.assertIn('reference_studies/' + file, guide)
            study = (root / 'reference_studies' / file).read_text(encoding='utf-8')
            self.assertIn('https://', study)
        self.assertIn('1280×720', guide)
        self.assertIn('controller focus', guide)

    def test_game_feel_syllabus_covers_requested_styles_and_production_guides(self):
        root = Path(__file__).resolve().parents[1] / 'command_center'
        guide = (root / 'GAME_FEEL_ACADEMY.md').read_text(encoding='utf-8')
        for topic in ('Fallout 3', 'Fallout: New Vegas', 'Fallout 4', 'Stealth',
                      'Diegetic', '1280×720', 'Startup', 'Photorealistic',
                      'Semi-realistic', 'Pixel', 'Music', 'VFX'):
            self.assertIn(topic, guide)
        for file in ('FALLOUT_PLAYSTYLES.md', 'INTERFACE_STYLES.md', 'STARTUP_SEQUENCES.md',
                     'ART_STYLES.md', 'SOUND_MUSIC.md', 'VFX_DESIGN.md'):
            self.assertIn('presentation_studies/' + file, guide)
            study = (root / 'presentation_studies' / file).read_text(encoding='utf-8')
            self.assertIn('https://', study)

    def test_core_disciplines_and_role_coverage_are_versioned(self):
        result = curriculum()
        self.assertEqual(result['version'], 6)
        self.assertEqual(result['curriculum_sha256'], spec_digest({k: v for k, v in result.items()
                                                                if k != 'curriculum_sha256'}))
        ids = {track['id'] for track in result['tracks']}
        self.assertTrue({'game-design', 'game-development', 'modeling', 'textures', 'storytelling'} <= ids)
        self.assertEqual(len(ids), 40)
        self.assertTrue({'cutscenes', 'game-audio', 'multiplayer', 'persistence', 'ai-encounters',
                         'production-pipeline'} <= ids)
        self.assertTrue({'player-enjoyment', 'replayability', 'player-research', 'visual-direction',
                         'visual-readability', 'experience-iteration'} <= ids)
        self.assertTrue({'motion-design', 'character-performance', 'environmental-storytelling',
                         'diegetic-narrative', 'voice-direction', 'voice-integration'} <= ids)
        self.assertTrue({'reference-narrative', 'reference-combat', 'reference-worlds',
                         'reference-traversal', 'reference-strategy', 'hud-excellence'} <= ids)
        self.assertTrue({'fallout-playstyles', 'interface-styles', 'startup-sequences',
                         'art-styles', 'sound-music', 'vfx-design'} <= ids)
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
            self.assertIn('/api/training-lab/assess', instruction)
            self.assertIn('/api/training-records', instruction)
            self.assertIn('Only the lead records or reviews practice', instruction)
            for track in curriculum()['tracks']:
                if role['id'] in track['roles']:
                    self.assertIn(track['title'], instruction)
                    for deliverable in track['deliverables']:
                        self.assertIn(deliverable, instruction)
                else:
                    self.assertNotIn(track['title'] + ':', instruction)
        with self.assertRaises(ValueError):
            training_instruction('unrecognized')
