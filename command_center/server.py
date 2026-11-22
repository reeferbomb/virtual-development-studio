"""Loopback-only Studio API and static command center; standard library only."""
import argparse
import fcntl
import json
import math
import mimetypes
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .acceptance import assess_acceptance
from .allocation import allocation
from .blueprints import blueprint
from .catalog import catalog
from .checkpoints import CheckpointStore, _locked_directory
from .defect_store import DefectStore
from .dependency_impact import dependency_impact
from .dispatch import scheduled_dispatch_plan
from .dispatch_cycle import dispatch_cycle
from .dossier import build_dossier
from .evidence_history import EvidenceHistory
from .forecast import forecast
from .handoff_store import HandoffStore
from .performance import profile_jobs
from .pipeline import Pipeline
from .portfolio import portfolio_plan
from .preflight import preflight
from .priorities import rank_tasks
from .projects import ProjectStore
from .provenance import spec_digest
from .quality_matrix import quality_matrix
from .quality_trends import quality_trends
from .recovery import capture_recovery
from .recovery_advice import recovery_advice
from .release_store import ReleaseStore
from .specialist_analytics import specialist_analytics
from .specialist_memory import specialist_memory
from .sprint_planner import plan_sprint
from .studio_curriculum import curriculum
from .supervisor import audit_project
from .task_store import TaskStore, _valid_digest
from .team import team_plan, release_summary
from .training_lab import assess_submission, lab_catalog, reject_duplicate_keys
from .training_progress import summarize_progress
from .training_records import TrainingRecordStore
from .work_orders import work_orders
from world.procedural import generate, plan_route

ROOT = Path(__file__).resolve().parents[1]
VERSION = '41.2'
LIMIT = 1024 * 1024
STATIC = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js',
          '/editor.js': 'editor.js', '/style.css': 'style.css', '/editor.css': 'editor.css'}
_BLUEPRINT_FILES = ('project.json', 'spec.json', 'task-board.json')
_AUDIT_FILES = _BLUEPRINT_FILES + ('defects.json', 'releases.json')


def _audit_source(read, *args):
    """Keep an unreadable source distinct from a healthy, empty evidence set."""
    try:
        return read(*args)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None


def _project_source_stamp(directory, names):
    """Identify the source files while holding the project directory lock."""
    stamp = []
    for name in names:
        try:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            stamp.append((name, info.st_dev, info.st_ino, info.st_mode, info.st_size,
                          info.st_mtime_ns, info.st_ctime_ns))
        except FileNotFoundError:
            stamp.append((name, None))
    return tuple(stamp)


def _job_stamp(project_id, jobs):
    return spec_digest([job for job in jobs if job['project_id'] == project_id]) if jobs is not None else None


def _validate_plan_approval(data):
    if not isinstance(data, dict) or set(data) != {'expected_revision', 'spec_sha256', 'plan_id'}:
        raise ValueError('Expected expected_revision, spec_sha256 and plan_id')
    if type(data['expected_revision']) is not int or data['expected_revision'] < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if not _valid_digest(data['spec_sha256']) or not _valid_digest(data['plan_id']):
        raise ValueError('spec_sha256 and plan_id must be lowercase SHA-256 digests')


def _approved_plan_action(data, preview, name):
    refresh = f'Refresh the {name} preview.'
    if preview['status'] != 'ready' or not preview['tasks']:
        raise FileExistsError(preview['reason'] or f'The {name} preview has no tasks to apply.')
    if data['expected_revision'] != preview['board_revision']:
        raise FileExistsError(f'Task board revision changed. {refresh}')
    if data['spec_sha256'] != preview['spec_sha256']:
        raise FileExistsError(f'Project specification changed. {refresh}')
    if data['plan_id'] != preview['plan_id']:
        raise FileExistsError(f'{name.capitalize()} preview changed. {refresh}')
    return {'expected_revision': data['expected_revision'], 'spec_sha256': data['spec_sha256'],
            'action': {'op': 'add_batch', 'tasks': preview['tasks']}}


class StudioService:
    def __init__(self, root, workspace):
        self.root = Path(root).resolve()
        self.workspace = Path(workspace).absolute()
        self.projects = ProjectStore(self.root, self.workspace)
        self.checkpoints = CheckpointStore(self.projects)
        self.pipeline = Pipeline(self.root, self.workspace)
        self.tasks = TaskStore(self.projects, job_lookup=self.pipeline.get)
        self.releases = ReleaseStore(self.projects, self.pipeline)
        self.defects = DefectStore(self.projects)
        self.evidence_history = EvidenceHistory(self.projects)
        self.handoffs = HandoffStore(self.projects)
        self.training_records = TrainingRecordStore(self.workspace)
        self.lock = threading.RLock()

    def status(self):
        tools = {}
        for name, candidates in [('blender', ('blender52', 'blender')), ('godot', ('godot',))]:
            executable = next((p for candidate in candidates if (p := shutil.which(candidate))), None)
            if executable:
                try:
                    result = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=5)
                    tools[name] = result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else 'Version unavailable'
                except (OSError, subprocess.TimeoutExpired):
                    tools[name] = 'Version unavailable'
            else:
                tools[name] = 'Not installed'
        return {'version': VERSION, 'tools': tools}

    def media(self, relative):
        data = catalog(self.root)
        allowed = {a['preview'] for a in data['assets'] if 'preview' in a} | {a['path'] for a in data['audio']}
        if relative not in allowed:
            raise FileNotFoundError('Media not in catalog')
        path = self.root / relative
        if path.resolve() != path or not path.is_file():
            raise FileNotFoundError('Media unavailable')
        return path

    def team(self, project_id):
        with self.lock:
            project = self.projects.get(project_id)
            plan = team_plan(project, self.pipeline.list())
            try:
                board = self.tasks.get(project_id)
            except (ValueError, OSError):
                plan['scheduling_error'] = 'Could not read the project task board.'
            else:
                plan['scheduled_dispatch_plan'] = scheduled_dispatch_plan(project, board)
            return plan

    def _evidence_jobs(self):
        jobs = self.pipeline.list()
        # The queue exposes unreadable records with no project identity.
        # Their owner cannot be determined for a project-scoped audit.
        if any(not isinstance(job, dict) or not job.get('project_id') for job in jobs):
            raise ValueError('Build history contains a record with unknown project identity')
        return jobs

    def performance(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project = self.projects.get(project_id)
            return profile_jobs(project, self._evidence_jobs())

    def work_orders(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project = self.projects.get(project_id)
            board = _audit_source(self.tasks.get, project_id)
            return work_orders(project, board)

    def specialist_memory(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project = self.projects.get(project_id)
            history = _audit_source(self.handoffs.get, project_id)
            return specialist_memory(project, history)

    def specialist_analytics(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project = self.projects.get(project_id)
            history = _audit_source(self.handoffs.get, project_id)
            return specialist_analytics(project, history)

    def allocation(self):
        with self.lock:
            return allocation(_audit_source(portfolio_plan, self.projects, self.tasks))

    def dispatch_cycle(self):
        with self.lock:
            return dispatch_cycle(_audit_source(portfolio_plan, self.projects, self.tasks))

    def _audit_snapshot(self, project_id):
        project = self.projects.get(project_id)
        jobs = _audit_source(self._evidence_jobs)
        board = _audit_source(self.tasks.get, project_id)
        registry = _audit_source(self.releases.get, project_id)
        defects = _audit_source(self.defects.get, project_id)
        performance = _audit_source(profile_jobs, project, jobs) if jobs is not None else None
        audit = audit_project(project, jobs, board, registry, defects, performance)
        return project, audit, board, defects, jobs, registry

    def supervisor(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            _, audit, *_ = self._audit_snapshot(project_id)
            return audit

    def sprint(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project, audit, board, *_ = self._audit_snapshot(project_id)
            return plan_sprint(project, audit, board)

    def _project_board(self, project_id):
        return self.projects.get(project_id), _audit_source(self.tasks.get, project_id)

    def blueprint(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return blueprint(*self._project_board(project_id))

    def apply_blueprint(self, project_id, data):
        _validate_plan_approval(data)
        with self.lock:
            with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
                file_stamp = _project_source_stamp(directory, _BLUEPRINT_FILES)
                preview = blueprint(*self._project_board(project_id))
            action = _approved_plan_action(data, preview, 'blueprint')

            def verify(directory):
                if _project_source_stamp(directory, _BLUEPRINT_FILES) != file_stamp:
                    raise FileExistsError('Blueprint sources changed. Refresh the blueprint preview.')

            # Release the shared lock before TaskStore acquires its exclusive lock.
            return self.tasks.apply(project_id, action, assert_snapshot=verify)

    def forecast(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return forecast(*self._project_board(project_id))

    def dependency_impact(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return dependency_impact(*self._project_board(project_id))

    def priorities(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return rank_tasks(*self._project_board(project_id))

    def recovery_advice(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project, board = self._project_board(project_id)
            history = _audit_source(self.handoffs.get, project_id)
            return recovery_advice(project, board, history)

    def _snapshot_guard(self, project_id, file_stamp, jobs):
        job_stamp = _job_stamp(project_id, jobs)

        def verify(directory):
            # The store has acquired its exclusive project lock. A different
            # service instance may have changed evidence after our shared read.
            if (_project_source_stamp(directory, _AUDIT_FILES) != file_stamp or
                    _job_stamp(project_id, _audit_source(self._evidence_jobs)) != job_stamp):
                raise FileExistsError('Project evidence changed. Refresh the sprint or audit and retry.')
        return verify

    def apply_sprint(self, project_id, data):
        _validate_plan_approval(data)
        with self.lock:
            with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
                file_stamp = _project_source_stamp(directory, _AUDIT_FILES)
                project, audit, board, _, jobs, _ = self._audit_snapshot(project_id)
                preview = plan_sprint(project, audit, board)
                verify = self._snapshot_guard(project_id, file_stamp, jobs)
            # The preview's shared directory lock is released before the store takes its write lock.
            return self.tasks.apply(project_id, _approved_plan_action(data, preview, 'sprint'),
                                    assert_snapshot=verify)

    def capture_evidence(self, project_id, data):
        with self.lock:
            with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
                file_stamp = _project_source_stamp(directory, _AUDIT_FILES)
                _, audit, _, _, jobs, _ = self._audit_snapshot(project_id)
                verify = self._snapshot_guard(project_id, file_stamp, jobs)
            return self.evidence_history.capture(project_id, data, audit, assert_snapshot=verify)

    def _acceptance_snapshot(self, project_id):
        project, audit, board, defects, *_ = self._audit_snapshot(project_id)
        history = _audit_source(self.evidence_history.get, project_id)
        return project, assess_acceptance(project, audit, board, defects, history)

    def acceptance(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return self._acceptance_snapshot(project_id)[1]

    def quality_matrix(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return quality_matrix(*self._acceptance_snapshot(project_id))

    def quality_trends(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project, audit, *_ = self._audit_snapshot(project_id)
            history = _audit_source(self.evidence_history.get, project_id)
            return quality_trends(project, audit, history)

    def _dossier_snapshot(self, project_id):
        project, audit, board, defects, jobs, registry = self._audit_snapshot(project_id)
        history = _audit_source(self.evidence_history.get, project_id)
        acceptance = assess_acceptance(project, audit, board, defects, history)
        handoffs = _audit_source(self.handoffs.get, project_id)
        return project, board, build_dossier(project, audit, acceptance, board, registry, jobs, handoffs)

    def dossier(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            return self._dossier_snapshot(project_id)[2]

    def preflight(self, project_id):
        with self.lock, _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH):
            project, board, dossier = self._dossier_snapshot(project_id)
            return preflight(project, dossier, forecast(project, board))


def create_server(service, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def response(self, body, content_type, status=200):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, value, status=200):
            self.response(json.dumps(value, allow_nan=False).encode(), 'application/json; charset=utf-8', status)

        def file_response(self, path):
            self.response(path.read_bytes(), mimetypes.guess_type(path.name)[0] or 'application/octet-stream')

        def body(self, *, object_pairs_hook=None):
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Expected application/json')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= LIMIT:
                raise ValueError('Invalid request length')
            result = json.loads(self.rfile.read(length), object_pairs_hook=object_pairs_hook)
            if not isinstance(result, dict):
                raise ValueError('Expected JSON object')
            return result

        def dispatch(self):
            try:
                host = self.headers.get('Host')
                valid_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
                if host not in valid_hosts or (self.headers.get('Origin') and self.headers['Origin'] != f'http://{host}'):
                    self.json_response({'error': 'Local same-origin requests only'}, 403)
                    return
                if self.command != 'GET' and self.headers.get('X-Studio-Request') != '1':
                    self.json_response({'error': 'Missing studio request header'}, 403)
                    return
                url = urlsplit(self.path)
                path = unquote(url.path)
                parts = path.strip('/').split('/')
                if self.command == 'GET':
                    if path in STATIC:
                        return self.file_response(service.root / 'command_center/ui' / STATIC[path])
                    if path == '/api/status': return self.json_response(service.status())
                    if path == '/api/catalog': return self.json_response(catalog(service.root))
                    if path == '/api/training': return self.json_response(curriculum())
                    if path == '/api/training-lab':
                        return self.json_response(lab_catalog())
                    if path == '/api/training-records':
                        return self.json_response(service.training_records.read())
                    if path == '/api/training-progress':
                        return self.json_response(summarize_progress(service.training_records.read()))
                    if path == '/api/projects': return self.json_response(service.projects.list())
                    if path == '/api/jobs': return self.json_response(service.pipeline.list())
                    if path == '/api/queue': return self.json_response(service.pipeline.queue())
                    if path == '/api/portfolio':
                        with service.lock:
                            portfolio = portfolio_plan(service.projects, service.tasks)
                        return self.json_response(portfolio)
                    if path == '/api/allocation': return self.json_response(service.allocation())
                    if path == '/api/dispatch-cycle': return self.json_response(service.dispatch_cycle())
                    if path == '/api/file': return self.file_response(service.media(parse_qs(url.query).get('path', [''])[0]))
                    if len(parts) == 3 and parts[:2] == ['api', 'projects']:
                        return self.json_response(service.projects.get(parts[2]))
                    if len(parts) == 4 and parts[:2] == ['api', 'projects']:
                        stores = {'checkpoint': service.checkpoints, 'tasks': service.tasks,
                                  'releases': service.releases, 'defects': service.defects,
                                  'evidence-history': service.evidence_history, 'handoffs': service.handoffs}
                        if parts[3] in stores:
                            with service.lock:
                                result = stores[parts[3]].get(parts[2])
                            return self.json_response(result)
                        if parts[3] == 'supervisor':
                            return self.json_response(service.supervisor(parts[2]))
                        if parts[3] == 'performance':
                            return self.json_response(service.performance(parts[2]))
                        if parts[3] == 'sprint':
                            return self.json_response(service.sprint(parts[2]))
                        if parts[3] == 'blueprint':
                            return self.json_response(service.blueprint(parts[2]))
                        if parts[3] == 'forecast':
                            return self.json_response(service.forecast(parts[2]))
                        if parts[3] == 'dependency-impact':
                            return self.json_response(service.dependency_impact(parts[2]))
                        if parts[3] == 'priorities':
                            return self.json_response(service.priorities(parts[2]))
                        if parts[3] == 'recovery-advice':
                            return self.json_response(service.recovery_advice(parts[2]))
                        if parts[3] == 'acceptance':
                            return self.json_response(service.acceptance(parts[2]))
                        if parts[3] == 'quality-matrix':
                            return self.json_response(service.quality_matrix(parts[2]))
                        if parts[3] == 'quality-trends':
                            return self.json_response(service.quality_trends(parts[2]))
                        if parts[3] == 'work-orders':
                            return self.json_response(service.work_orders(parts[2]))
                        if parts[3] == 'specialist-memory':
                            return self.json_response(service.specialist_memory(parts[2]))
                        if parts[3] == 'specialist-analytics':
                            return self.json_response(service.specialist_analytics(parts[2]))
                        if parts[3] == 'dossier':
                            return self.json_response(service.dossier(parts[2]))
                        if parts[3] == 'preflight':
                            return self.json_response(service.preflight(parts[2]))
                        if parts[3] == 'recovery':
                            return self.json_response(capture_recovery(service.projects, parts[2]))
                    if len(parts) == 3 and parts[:2] == ['api', 'jobs']:
                        return self.json_response(service.pipeline.get(parts[2]))
                    if len(parts) == 4 and parts[:2] == ['api', 'jobs'] and parts[3] == 'log':
                        return self.json_response({'log': service.pipeline.log(parts[2])})
                    if len(parts) == 3 and parts[:2] == ['api', 'team']:
                        return self.json_response(service.team(parts[2]))
                    if len(parts) == 3 and parts[:2] == ['api', 'release']:
                        return self.json_response(release_summary(service.projects.get(parts[2]), service.pipeline.list()))
                elif self.command in ('POST', 'PUT'):
                    if self.command == 'POST' and path == '/api/training-lab/assess':
                        data = self.body(object_pairs_hook=reject_duplicate_keys)
                        if set(data) != {'exercise_id', 'submission'}:
                            raise ValueError('Expected exercise_id and submission')
                        return self.json_response(assess_submission(data['exercise_id'], data['submission']))
                    if self.command == 'POST' and path == '/api/training-records':
                        data = self.body(object_pairs_hook=reject_duplicate_keys)
                        return self.json_response(service.training_records.apply(data))
                    data = self.body()
                    with service.lock:
                        if self.command == 'POST' and path == '/api/projects' and set(data) == {'name', 'kind'}:
                            return self.json_response(service.projects.create(data['name'], data['kind']), 201)
                        if (self.command == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'jobs']
                                and parts[3] in ('cancel', 'retry')):
                            if data:
                                raise ValueError('Expected an empty object')
                            if parts[3] == 'cancel':
                                return self.json_response(service.pipeline.cancel(parts[2]))
                            return self.json_response(service.pipeline.retry(parts[2]), 202)
                        if len(parts) == 4 and parts[:2] == ['api', 'projects']:
                            if self.command == 'PUT' and parts[3] == 'checkpoint':
                                return self.json_response(service.checkpoints.save(parts[2], data))
                            if self.command == 'PUT' and parts[3] == 'tasks':
                                return self.json_response(service.tasks.apply(parts[2], data))
                            if self.command == 'PUT' and parts[3] == 'releases':
                                return self.json_response(service.releases.apply(parts[2], data))
                            if self.command == 'PUT' and parts[3] == 'defects':
                                return self.json_response(service.defects.apply(parts[2], data))
                            if self.command == 'POST' and parts[3] == 'sprint':
                                return self.json_response(service.apply_sprint(parts[2], data))
                            if self.command == 'POST' and parts[3] == 'blueprint':
                                return self.json_response(service.apply_blueprint(parts[2], data))
                            if self.command == 'POST' and parts[3] == 'evidence-history':
                                return self.json_response(service.capture_evidence(parts[2], data))
                            if self.command == 'POST' and parts[3] == 'handoffs':
                                return self.json_response(service.handoffs.apply(parts[2], data))
                            if self.command == 'POST' and parts[3] == 'generate' and set(data) == {'seed','count'}:
                                if service.projects.get(parts[2])['kind'] != 'world':
                                    raise ValueError('Generation is for world projects')
                                spec = generate(data['seed'], data['count'])
                                route = plan_route(spec)
                                return self.json_response({'spec':spec,'route':route,'route_m':sum(math.dist(a,b) for a,b in zip(route,route[1:]))})
                            if self.command == 'PUT' and parts[3] == 'spec' and set(data) == {'spec'}:
                                return self.json_response(service.projects.save_spec(parts[2], data['spec']))
                            if self.command == 'POST' and parts[3] == 'build':
                                if set(data) - {'priority'}:
                                    raise ValueError('Build accepts only an optional priority')
                                project_dir = service.projects.directory(parts[2])
                                job = service.pipeline.submit(project_dir, priority=data.get('priority', 3))
                                return self.json_response(job, 202)
                self.json_response({'error': 'Unknown route or request'}, 404)
            except FileExistsError as exc:
                self.json_response({'error': str(exc)}, 409)
            except (FileNotFoundError, KeyError):
                self.json_response({'error': 'Not found'}, 404)
            except (ValueError, TypeError, OverflowError, RecursionError) as exc:
                self.json_response({'error': str(exc)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.json_response({'error': 'Internal studio error'}, 500)

        do_GET = do_POST = do_PUT = dispatch

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=ROOT.parent / 'studio-workspace')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    service = StudioService(ROOT, args.workspace)
    server = create_server(service, args.port)
    print(f'STUDIO_COMMAND_CENTER_READY http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
