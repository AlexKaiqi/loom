"""Verify R/E references from original R rows and original JetStream bytes."""
from pathlib import Path
import copy

from lore_control.values import decode, identifier
from lore_events.input_files import validate
from lore_events.persistence import read_file
from lore_events.values import encode, sha, same
from .event_reader import JetStreamReader


def require(condition):
    if not condition:
        raise ValueError('original event reference or scope differs')


class OriginalControlRead:
    """The owner's read query semantics without opening another transaction."""
    def __init__(self, control):
        self.control = control

    def query(self, principal, request_id):
        identifier(request_id)
        with self.control._lock:
            row = self.control._get_request(request_id)
            self.control._authorize(principal, row['namespace'])
            return self.control._request_value(row)


class EventReferences:
    def __init__(self, control, events, reader):
        self.control, self.events, self.reader = control, events, reader
        self.originals = copy.copy(events)
        self.originals.control = OriginalControlRead(control)

    def _row(self, request_id):
        # The checker can run inside the owner's transaction; never start a second one.
        with self.control._lock:
            row = self.control.db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            require(row is not None)
            return self.control._request_value(row)

    def _receipt(self, ref, expected):
        row = self._row(ref['request_id'])
        require(row['kind'] == 'event' and ref['delivery_owner'] == 'E')
        require(type(expected) is dict and set(expected) == {'request_id', 'namespace', 'source', 'delivery_owner', 'request_digest'})
        require(all(same(ref.get(k), v) for k, v in expected.items()))
        outcome = ref['outcome']
        if outcome == 'positive':
            selected = ref['facility_ref']
            msg = self.reader.read(self.events._stream(row['namespace']), selected['sequence'])
            original = self.originals._facility(row, msg)
        elif outcome == 'negative':
            path = self.events._receipt_path(row)
            original = self.events._negative(row, read_file(path), path)
        else:
            return False
        return same(ref, self.events._wrapper(row, original, outcome))

    def _input(self, ref, expected):
        require(type(expected) is dict and set(expected) == {'invocation_id', 'binding'})
        row = self._row(expected['invocation_id'])
        binding = expected['binding']
        require(row['kind'] == 'invocation' and same(row['payload']['input_binding'], binding))
        require(ref['owner'] == 'E' and ref['kind'] == 'input' and ref['id'] == row['id'])
        files, metadata = validate(ref, binding, self.events.profile['input_root'])
        raws = []; previous = 0
        for event_ref in metadata['event_refs']:
            msg = self.reader.read(self.events._stream(binding['namespace']), event_ref['sequence'])
            body = self.originals._message(msg, binding['namespace'])
            original = self.originals._facility(self._row(body['request_id']), msg)
            require(same(original, event_ref) and previous < msg.seq and
                    metadata['range']['start_sequence'] <= msg.seq <= metadata['range']['end_sequence'])
            previous = msg.seq; raws.append(msg.data + b'\n')
        return b''.join(raws) == files['events.jsonl']

    def _observation(self, ref, expected):
        require(set(ref) == {'owner', 'kind', 'id', 'namespace', 'resource_id', 'revision', 'sha256'})
        require(ref['owner'] == 'R' and ref['kind'] == 'registration' and
                set(expected) == {'namespace', 'source', 'event_name'} and expected['event_name'] == 'surface.registered')
        with self.control._lock:
            row = self.control.db.execute('SELECT binding_json,response_json FROM operations WHERE id=?', (ref['id'],)).fetchone()
            require(row is not None)
            binding, result = decode(row[0]), decode(row[1])
        require(binding['op'] == 'register' and binding['kind'] == result['kind'] == 'surface')
        require(binding['principal'] == expected['source'] and binding['namespace'] == result['namespace'] == ref['namespace'] == expected['namespace'])
        require(binding['resource_id'] == result['id'] == ref['resource_id'] and type(ref['revision']) is int and ref['revision'] == result['revision'])
        require(binding['harness_ref'] == result['harness_ref'] and binding['grants'] == result['grants'])
        require(type(result['dev']) is int and type(result['ino']) is int and Path(result['path']).is_absolute())
        return sha(row[1].encode()) == ref['sha256'] and encode(binding) == row[0].encode() and encode(result) == row[1].encode()

    def __call__(self, ref, purpose, expected=None):
        try:
            if type(ref) is not dict:
                return False
            if purpose == 'receipt':
                return self._receipt(ref, expected)
            if purpose == 'input':
                return self._input(ref, expected)
            if purpose == 'observation':
                return self._observation(ref, expected)
            return False
        except Exception:
            # An unavailable original cannot authorize a receipt or repair its source.
            return False
