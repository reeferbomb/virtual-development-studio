"""Replay a bounded authoritative multiplayer session without sockets or a game engine."""

from .lab_gameplay import _array, _choice, _integer, _object, _result


TRACK = {
    'id': 'multiplayer', 'title': 'Multiplayer authority and session recovery',
    'roles': ['architecture', 'gameplay', 'verification', 'build_operations'],
    'workflow': [
        'Assign authority per entity. Define the session identity, command owner, permitted moves, '
        'sequence policy and snapshot fields before implementing prediction.',
        'Apply local input immediately for responsiveness. On a server snapshot, restore its position, '
        'drop resolved inputs and replay outstanding input in order. Measure the visible correction.',
        'Schedule delivery independently of input. Vary latency and packet order, repeat deliveries '
        'and verify server position and acknowledgement after each accepted or rejected command.',
        'Trace join, disconnect, reconnect and teardown. Preserve authoritative world state, rebind '
        'ownership, invalidate the old session and start the new sequence from a known snapshot.',
    ],
    'deliverables': [
        'Authority and ownership table with command validation, retry rules and the session lifecycle.',
        'Packet and snapshot timeline with tick, session, sequence, server position and predicted position.',
    ],
    'verification': [
        'Replay the same inputs and delivery schedule twice. Check that duplicates, gaps, invalid '
        'moves and commands from another owner leave the authoritative state unchanged.',
        'Inject a delayed packet across reconnect. Confirm fresh commands work and the replica converges '
        'after outstanding moves settle. Record live network, transport and engine tests separately.',
    ],
    'exercise': 'Predict each observed state in an authoritative cart session with delayed delivery, '
                'an optimistic client, rejected moves, a disconnect and a reconnect.',
}


def _event(op, result, server, client, ack, epoch=1, online=True, **fields):
    return dict(op=op, **fields, expect=dict(result=result, server=server, client=client,
                                             ack=ack, epoch=epoch, online=online))


EXERCISES = [{
    'id': 'multiplayer', 'title': 'Reconcile the relay cart',
    'brief': 'Start online in epoch 1 with cart positions and server acknowledgement (ack) at zero. '
             'Submit at most 32 events. send queues a packet tagged with the current epoch, actor '
             '(owner or guest), seq (1–32) and delta (−9 to 9). Only owner input predicts the full '
             'delta on the client. deliver names a packet by its 1-based send event number and may retry it. '
             'In order, reject offline, stale-session, unowned, duplicate (seq ≤ ack), out-of-order '
             '(seq > ack + 1), or invalid (delta outside −2, −1, 1, 2). Otherwise add delta on the '
             'server and set ack to seq. Delivery never updates the displayed position. '
             'An online snapshot restores server position and replays pending owner packets with seq > ack. '
             'An out-of-order packet stays pending for retry. Resolved packets drop from the pending list. '
             'disconnect freezes positions and ack. Offline send, deliver and snapshot return offline '
             'without creating packets or changing state. reconnect advances the epoch, resets ack, clears '
             'predictions and restores server position. Repeated disconnect and reconnect return '
             'already-offline and already-online respectively. On every event predict result, server, '
             'client, ack, epoch and online. Demonstrate all four authority rejections and an applied move, '
             'prediction during latency, snapshot replay of pending movement and correction of drift. '
             'Deliver a current packet while offline. On the next reconnect reject a packet from that '
             'interrupted epoch, then apply a fresh move. '
             'Finish online at a snapshot or reconnect with both positions equal and no pending owner inputs.',
    'criteria': [
        {'id': 'observations', 'label': 'Predict the exact result and state of every event'},
        {'id': 'authority', 'label': 'Apply owned moves and reject duplicates, gaps, invalid and unowned moves'},
        {'id': 'prediction', 'label': 'Demonstrate prediction, replay of pending input and a snapshot correction'},
        {'id': 'session', 'label': 'Handle offline delivery, stale packets and fresh post-reconnect input'},
        {'id': 'convergence', 'label': 'Converge at a final online snapshot or reconnect with no pending inputs'},
    ],
    'example': {'events': [
        _event('send', 'sent', 0, 1, 0, actor='owner', seq=1, delta=1),
        _event('send', 'sent', 0, 3, 0, actor='owner', seq=2, delta=2),
        _event('deliver', 'out-of-order', 0, 3, 0, packet=2),
        _event('deliver', 'applied', 1, 3, 1, packet=1),
        _event('snapshot', 'snapshot', 1, 3, 1),
        _event('deliver', 'applied', 3, 3, 2, packet=2),
        _event('deliver', 'duplicate', 3, 3, 2, packet=1),
        _event('send', 'sent', 3, 3, 2, actor='guest', seq=3, delta=1),
        _event('deliver', 'unowned', 3, 3, 2, packet=8),
        _event('send', 'sent', 3, 7, 2, actor='owner', seq=3, delta=4),
        _event('deliver', 'invalid', 3, 7, 2, packet=10),
        _event('snapshot', 'snapshot', 3, 3, 2),
        _event('send', 'sent', 3, 2, 2, actor='owner', seq=3, delta=-1),
        _event('disconnect', 'disconnected', 3, 2, 2, online=False),
        _event('deliver', 'offline', 3, 2, 2, online=False, packet=13),
        _event('reconnect', 'reconnected', 3, 3, 0, 2),
        _event('deliver', 'stale-session', 3, 3, 0, 2, packet=13),
        _event('send', 'sent', 3, 1, 0, 2, actor='owner', seq=1, delta=-2),
        _event('deliver', 'applied', 1, 1, 1, 2, packet=18),
        _event('snapshot', 'snapshot', 1, 1, 1, 2),
    ]},
}]


_OPERATIONS = ('send', 'deliver', 'snapshot', 'disconnect', 'reconnect')
_RESULTS = ('sent', 'applied', 'out-of-order', 'duplicate', 'invalid', 'unowned', 'offline',
            'stale-session', 'snapshot', 'disconnected', 'reconnected', 'already-offline', 'already-online')
_AUTHORITY = {'applied', 'out-of-order', 'duplicate', 'invalid', 'unowned'}


def _validate_event(event, number):
    where = f'Event {number}'
    if type(event) is not dict:
        raise ValueError(f'{where} must be an object')
    op = event.get('op')
    _choice(op, _OPERATIONS, where + '.op')
    fields = {'send': ('actor', 'seq', 'delta'), 'deliver': ('packet',)}.get(op, ())
    _object(event, ('op', 'expect') + fields, where)
    if op == 'send':
        _choice(event['actor'], ('owner', 'guest'), where + '.actor')
        _integer(event['seq'], 1, 32, where + '.seq')
        _integer(event['delta'], -9, 9, where + '.delta')
    elif op == 'deliver':
        _integer(event['packet'], 1, 32, where + '.packet')

    expected = event['expect']
    _object(expected, ('result', 'server', 'client', 'ack', 'epoch', 'online'), where + '.expect')
    _choice(expected['result'], _RESULTS, where + '.expect.result')
    for field in ('server', 'client'):
        _integer(expected[field], -288, 288, where + '.expect.' + field)
    _integer(expected['ack'], 0, 32, where + '.expect.ack')
    _integer(expected['epoch'], 1, 33, where + '.expect.epoch')
    if type(expected['online']) is not bool:
        raise ValueError(f'{where}.expect.online requires a boolean')


class _Session:
    def __init__(self):
        self.online = True
        self.epoch = 1
        self.server = self.client = self.ack = 0
        self.packets = {}
        self.pending = {}
        self.deliveries = set()
        self.predicted = self.replayed = self.corrected = False
        self.offline_drop_epoch = self.stale_rejection_epoch = None
        self.recovered = False

    def _receive(self, number):
        if number not in self.packets:
            raise ValueError('Delivery must reference a preceding online send event')
        epoch, actor, seq, delta = self.packets[number]
        if not self.online:
            if epoch == self.epoch:
                self.offline_drop_epoch = epoch
            return 'offline'
        if epoch != self.epoch:
            if epoch == self.epoch - 1 and epoch == self.offline_drop_epoch:
                self.stale_rejection_epoch = self.epoch
            return 'stale-session'
        if actor != 'owner':
            return 'unowned'
        if seq > self.ack + 1:
            return 'out-of-order'
        self.pending.pop(number, None)
        if seq <= self.ack:
            return 'duplicate'
        if delta not in (-2, -1, 1, 2):
            return 'invalid'
        self.server += delta
        self.ack = seq
        self.recovered |= self.epoch == self.stale_rejection_epoch
        return 'applied'

    def step(self, event, number):
        op = event['op']
        if op == 'deliver':
            result = self._receive(event['packet'])
            self.deliveries.add(result)
            return result
        if op == 'disconnect':
            if not self.online:
                return 'already-offline'
            self.online = False
            return 'disconnected'
        if op == 'reconnect':
            if self.online:
                return 'already-online'
            self.online = True
            self.epoch += 1
            self.ack = 0
            self.pending.clear()
            self.client = self.server
            return 'reconnected'
        if not self.online:
            return 'offline'
        if op == 'send':
            actor, seq, delta = event['actor'], event['seq'], event['delta']
            self.packets[number] = (self.epoch, actor, seq, delta)
            if actor == 'owner':
                self.pending[number] = (seq, delta)
                self.client += delta
                self.predicted |= self.client != self.server
            return 'sent'

        # An authoritative snapshot includes ack, so an already-acknowledged
        # sequence can be discarded even if this particular copy never arrived.
        self.pending = {i: move for i, move in self.pending.items() if move[0] > self.ack}
        previous = self.client
        self.client = self.server + sum(delta for seq, delta in self.pending.values())
        self.replayed |= self.client != self.server
        self.corrected |= self.client != previous
        return 'snapshot'


def assess(exercise_id, submission):
    if exercise_id != 'multiplayer':
        raise ValueError('Unknown multiplayer exercise')
    _object(submission, ('events',), 'Multiplayer session')
    events = submission['events']
    _array(events, 32, 'events')
    session = _Session()
    first_mismatch = None
    last = None
    for number, event in enumerate(events, 1):
        _validate_event(event, number)
        last = session.step(event, number)
        observed = dict(result=last, server=session.server, client=session.client,
                        ack=session.ack, epoch=session.epoch, online=session.online)
        if first_mismatch is None:
            for field, actual in observed.items():
                if actual != event['expect'][field]:
                    first_mismatch = f'Event {number} ({event["op"]}) observed {field} = {actual}.'
                    break

    missing = sorted(_AUTHORITY - session.deliveries)
    converged = (session.predicted and last in ('snapshot', 'reconnected') and session.online
                 and session.client == session.server and not session.pending)
    return [
        _result('observations', bool(events) and first_mismatch is None,
                first_mismatch or f'{len(events)} event observations matched the replay.'),
        _result('authority', not missing, 'Missing delivery outcomes: ' + (', '.join(missing) or 'none') + '.'),
        _result('prediction', session.predicted and session.replayed and session.corrected,
                f'Predicted divergence: {session.predicted}. Pending movement replayed: {session.replayed}. '
                f'Snapshot corrected display: {session.corrected}.'),
        _result('session', session.recovered, f'Offline delivery: {"offline" in session.deliveries}. '
                f'Stale session rejected: {"stale-session" in session.deliveries}. '
                f'Fresh move after the same session recovery: {session.recovered}.'),
        _result('convergence', converged,
                f'Last result: {last}. Server {session.server}, client {session.client}, '
                f'pending owner inputs {len(session.pending)}, online {session.online}.'),
    ]
