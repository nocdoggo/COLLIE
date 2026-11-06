"""Invented-only tests of the in-memory schema-shaped JSONL projection."""

import builtins
from copy import deepcopy
from hashlib import sha256
import json
import os
import socket

import pytest

from analysis.coling.followup import oss_jsonl_synthetic as candidate


ITEM_A = 'SYNTH-ITEM-A'
ITEM_B = 'SYNTH-ITEM-B'
ITEM_C = 'SYNTH-ITEM-C'
TEMPLATE_SHA = sha256(b'SYNTH-TEMPLATE-LITERAL-V1').hexdigest()
SERVED = {'model': 'SYNTH-MODEL-ID', 'provider': 'SYNTH-PROVIDER',
          'provider_names': ['SYNTH-PROVIDER'], 'metadata': None}


def literal(label='ALPHA'):
    return {'statement_type': 'none', 'interval': 'ABSTAIN', 'certainty': 'no_statement',
            'stale': False, 'quote': 'SYNTH-QUOTE-' + label}


def answer(label='ALPHA'):
    return json.dumps(literal(label), sort_keys=True, separators=(',', ':'))


def prompt_hash(item, sample, attempt, first=None):
    material = f'SYNTH-PROMPT-V1|{item}|{sample}|{attempt}'
    if attempt:
        material += '|' + sha256(first.encode('ascii')).hexdigest()
    return sha256(material.encode('ascii')).hexdigest()


def response(item=ITEM_A, sample=0, attempt=0, text=None, first=None):
    text = answer() if text is None else text
    return {'item_id': item, 'sample': sample, 'attempt': attempt,
            'prompt_sha256': prompt_hash(item, sample, attempt, first), 'text': text,
            'served': None if text == '' else deepcopy(SERVED)}


def attempt_row(row, *, cache_hit=False):
    refused = row['text'] == ''
    return {'attempt': row['attempt'], 'prompt_sha256': row['prompt_sha256'], 'cache_hit': cache_hit,
            'refused': refused, 'served_model': None if refused else 'SYNTH-MODEL-ID',
            'served_provider': None if refused else 'SYNTH-PROVIDER',
            'prompt_tokens': 0 if refused else 10, 'completion_tokens': 0 if refused else 5,
            'total_tokens': 0 if refused else 15, 'billable_output_tokens': 0 if refused else 6,
            'usd': 0 if refused else 0.000001}


def reading(*responses):
    first = responses[0]
    if first['text'] == '':
        status, parsed, errors, echo = 'refused', None, ['no JSON object found'], 'refused'
    elif first['text'] != 'SYNTH-NONJSON':
        status, parsed, errors, echo = 'ok', json.loads(first['text']), [], 'ok'
    else:
        second = responses[1]
        errors, echo = ['no JSON object found'], 'ok'
        if second['text'] not in ('', 'SYNTH-NONJSON'):
            status, parsed = 'repaired', json.loads(second['text'])
        else:
            status, parsed = 'failed', None
            errors.append('repair: no JSON object found')
    return {'item_id': first['item_id'], 'period': 'SYNTH-PERIOD', 'sample': first['sample'],
            'model': 'SYNTH-MODEL', 'model_id': 'SYNTH-MODEL-ID', 'provider_pin': 'SYNTH-PROVIDER',
            'template': 'SYNTH-TEMPLATE-LITERAL', 'template_sha256': TEMPLATE_SHA,
            'decoding': 'SYNTH-DECODING-ORIGINAL-DEFAULT', 'temperature': 0.0, 'mask_names': False,
            'shift_years': 0, 'track_record_sha256': None, 'condition': 'SYNTH-CONDITION-ORIGINAL-DEFAULT',
            'status': status, 'fallback': None if status in {'ok', 'repaired'} else 'abstain',
            'echo': echo, 'reading': parsed, 'errors': errors, 'warnings': [],
            'attempts': [attempt_row(row) for row in responses]}


def jsonl(*rows, spacious=False):
    return b''.join((('  ' if spacious else '')
                     + json.dumps(row, sort_keys=not spacious, ensure_ascii=False,
                                  separators=(', ', ': ') if spacious else (',', ':'))
                     + ('  ' if spacious else '') + '\n').encode('utf-8') for row in rows)


def inventory(assignments, readings=b'', responses=b''):
    return candidate.SyntheticRunInventory('SYNTH-RUN-A', tuple(assignments),
                                           sha256(readings).hexdigest(), sha256(responses).hexdigest())


def merge(assignments, old_readings=b'', old_responses=b'', new_readings=b'', new_responses=b''):
    return candidate.merge_synthetic_checkpoint(
        inventory(assignments, old_readings, old_responses), original_readings=old_readings,
        original_responses=old_responses, added_readings=new_readings, added_responses=new_responses,
        synthetic_only=True,
    )


def test_preserves_both_original_jsonl_byte_strings_and_reuses_orphaned_response():
    a = response(ITEM_A)
    b0 = response(ITEM_B, 1, text='SYNTH-NONJSON')
    b1 = response(ITEM_B, 1, 1, answer('BETA'), first=b0['text'])
    c = response(ITEM_C, 0, text=answer('GAMMA'))
    old_readings = jsonl(reading(a), spacious=True)
    old_responses = jsonl(a, b0, spacious=True)
    new_readings = jsonl(reading(b0, b1), reading(c))
    new_responses = jsonl(b1, c)
    assignments = ((ITEM_A, 0), (ITEM_B, 1), (ITEM_C, 0), ('SYNTH-ITEM-D', 0))
    result = merge(assignments, old_readings, old_responses, new_readings, new_responses)
    assert result.readings_bytes == old_readings + new_readings
    assert result.responses_bytes == old_responses + new_responses
    assert result.original_readings_sha256 == sha256(old_readings).hexdigest()
    assert result.original_responses_sha256 == sha256(old_responses).hexdigest()
    assert result.combined_readings_sha256 == sha256(result.readings_bytes).hexdigest()
    assert result.combined_responses_sha256 == sha256(result.responses_bytes).hexdigest()
    assert (result.original_reading_rows, result.added_reading_rows) == (1, 2)
    assert (result.original_response_rows, result.added_response_rows) == (2, 2)
    assert (result.outstanding_assignments, result.orphan_response_rows) == (1, 0)


def test_orphaned_answer_can_be_referenced_without_adding_another_response():
    old = response(ITEM_A, text=answer('BETA'))
    old_responses = jsonl(old, spacious=True)
    addition = jsonl(reading(old))
    result = merge(((ITEM_A, 0),), old_responses=old_responses, new_readings=addition)
    assert result.responses_bytes == old_responses and result.added_response_rows == 0
    assert result.readings_bytes == addition
    assert result.outstanding_assignments == result.orphan_response_rows == 0


def test_unfinished_orphan_remains_explicitly_outstanding():
    old = response(ITEM_A, text='SYNTH-NONJSON')
    original = jsonl(old, spacious=True)
    result = merge(((ITEM_A, 0), (ITEM_B, 0)), old_responses=original)
    assert result.responses_bytes == original and result.readings_bytes == b''
    assert (result.outstanding_assignments, result.orphan_response_rows) == (2, 1)


def test_two_orphaned_attempts_can_complete_a_row_without_new_responses():
    first = response(ITEM_A, text='SYNTH-NONJSON')
    second = response(ITEM_A, attempt=1, text=answer('BETA'), first=first['text'])
    old = jsonl(first, second)
    result = merge(((ITEM_A, 0),), old_responses=old, new_readings=jsonl(reading(first, second)))
    assert result.responses_bytes == old and result.added_response_rows == 0
    assert result.outstanding_assignments == result.orphan_response_rows == 0


def test_new_response_without_a_completed_reading_stays_orphaned():
    first = response(ITEM_A, text='SYNTH-NONJSON')
    result = merge(((ITEM_A, 0),), new_responses=jsonl(first))
    assert (result.outstanding_assignments, result.orphan_response_rows) == (1, 1)


@pytest.mark.parametrize('case', ['ok', 'repaired', 'failed_bad', 'failed_refused', 'refused'])
def test_supported_literal_statuses_are_derived_from_closed_responses(case):
    if case == 'ok':
        replies = (response(ITEM_A, text=answer('BETA')),)
    elif case == 'refused':
        replies = (response(ITEM_A, text=''),)
    else:
        first = response(ITEM_A, text='SYNTH-NONJSON')
        text = answer('GAMMA') if case == 'repaired' else '' if case == 'failed_refused' else 'SYNTH-NONJSON'
        replies = (first, response(ITEM_A, attempt=1, text=text, first=first['text']))
    result = merge(((ITEM_A, 0),), new_readings=jsonl(reading(*replies)), new_responses=jsonl(*replies))
    assert result.outstanding_assignments == result.orphan_response_rows == 0


def test_same_item_different_samples_are_distinct_assignments():
    a0 = response(ITEM_A, 0)
    a1 = response(ITEM_A, 1, text=answer('BETA'))
    result = merge(((ITEM_A, 0), (ITEM_A, 1)), new_readings=jsonl(reading(a0), reading(a1)),
                   new_responses=jsonl(a0, a1))
    assert result.added_reading_rows == 2 and result.outstanding_assignments == 0


def test_original_completed_row_cannot_be_silently_repaired_by_a_later_response():
    a = response(ITEM_A)
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='response attempts'):
        merge(((ITEM_A, 0),), old_readings=jsonl(reading(a)), new_responses=jsonl(a))


@pytest.mark.parametrize('location', ['original', 'addition', 'cross'])
def test_duplicate_item_sample_readings_are_refused_even_if_identical(location):
    a = response(ITEM_A)
    row, reply = jsonl(reading(a)), jsonl(a)
    if location == 'original':
        args = dict(old_readings=row + row, old_responses=reply)
    elif location == 'addition':
        args = dict(new_readings=row + row, new_responses=reply)
    else:
        args = dict(old_readings=row, old_responses=reply, new_readings=row)
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='duplicat'):
        merge(((ITEM_A, 0),), **args)


@pytest.mark.parametrize('location', ['original', 'addition', 'cross'])
def test_duplicate_response_attempts_are_refused_even_if_identical(location):
    a = response(ITEM_A)
    reply = jsonl(a)
    if location == 'original':
        args = dict(old_responses=reply + reply)
    elif location == 'addition':
        args = dict(new_responses=reply + reply)
    else:
        args = dict(old_responses=reply, new_responses=reply)
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='duplicat'):
        merge(((ITEM_A, 0),), **args)


def test_completed_original_reading_cannot_gain_a_new_repair_attempt():
    first = response(ITEM_A, text='SYNTH-NONJSON')
    second = response(ITEM_A, attempt=1, text=answer(), first=first['text'])
    # Both response slots of this completed row already exist; attempting to
    # add either one must fail rather than overwrite or duplicate it.
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='duplicat'):
        merge(((ITEM_A, 0),), old_readings=jsonl(reading(first, second)),
              old_responses=jsonl(first, second), new_responses=jsonl(second))


@pytest.mark.parametrize('target', ['reading', 'response'])
def test_unassigned_items_and_samples_are_never_merged(target):
    b = response(ITEM_B, 1)
    kwargs = dict(new_readings=jsonl(reading(b)), new_responses=jsonl(b))
    if target == 'response':
        kwargs['new_readings'] = b''
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='assign'):
        merge(((ITEM_A, 0),), **kwargs)


def test_repair_without_first_response_or_after_valid_first_answer_is_refused():
    first = response(ITEM_A, text='SYNTH-NONJSON')
    second = response(ITEM_A, attempt=1, text=answer(), first=first['text'])
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='lacks its first'):
        merge(((ITEM_A, 0),), new_responses=jsonl(second))
    good = response(ITEM_A)
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='repair'):
        merge(((ITEM_A, 0),), new_responses=jsonl(good, second))


@pytest.mark.parametrize(('field', 'value'), [
    ('period', 'not-synthetic'), ('model', 'other'), ('model_id', 'other'),
    ('provider_pin', 'other'), ('template', 'other'), ('template_sha256', '0' * 64),
    ('decoding', 'SYNTH-CAPPED'), ('temperature', 1), ('temperature', False),
    ('mask_names', True), ('mask_names', 0), ('shift_years', 1), ('shift_years', False),
    ('track_record_sha256', '0' * 64), ('condition', 'other'), ('status', 'failed'),
    ('fallback', 'abstain'), ('echo', 'mismatch'), ('errors', ['invented']),
    ('warnings', ['invented']), ('reading', None),
])
def test_changed_reading_identity_or_derived_content_is_refused(field, value):
    a = response(ITEM_A)
    row = reading(a)
    row[field] = value
    with pytest.raises(candidate.SyntheticCheckpointRefusal):
        merge(((ITEM_A, 0),), new_readings=jsonl(row), new_responses=jsonl(a))


def test_wrong_boolean_inside_literal_reading_is_not_equal_to_false():
    a = response(ITEM_A)
    row = reading(a)
    row['reading']['stale'] = 0
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='parsed content'):
        merge(((ITEM_A, 0),), new_readings=jsonl(row), new_responses=jsonl(a))


@pytest.mark.parametrize(('field', 'value'), [
    ('attempt', True), ('prompt_sha256', '0' * 64), ('cache_hit', 1), ('refused', True),
    ('served_model', None), ('served_provider', 'different'), ('prompt_tokens', True),
    ('completion_tokens', -1), ('total_tokens', 1), ('billable_output_tokens', 1),
    ('usd', -0.01), ('usd', 2), ('usd', True),
])
def test_attempt_metadata_is_checked_against_its_synthetic_response(field, value):
    a = response(ITEM_A)
    row = reading(a)
    row['attempts'][0][field] = value
    with pytest.raises(candidate.SyntheticCheckpointRefusal):
        merge(((ITEM_A, 0),), new_readings=jsonl(row), new_responses=jsonl(a))


@pytest.mark.parametrize(('field', 'value'), [
    ('prompt_sha256', '0' * 64), ('attempt', True), ('served', None),
    ('text', 'SYNTH-ARBITRARY-TEXT'), ('item_id', 'not-synthetic'), ('sample', False),
])
def test_bad_response_identity_or_free_text_is_refused(field, value):
    a = response(ITEM_A)
    a[field] = value
    with pytest.raises(candidate.SyntheticCheckpointRefusal):
        merge(((ITEM_A, 0),), new_responses=jsonl(a))


@pytest.mark.parametrize('raw', [b'{}', b'{}\r\n', b'{}\n\n', b'\xff\n', b'[]\n',
                                 b'{"x": NaN}\n', b'{"x": Infinity}\n',
                                 b'{"x": 1e999999999999999999999999999999999999}\n',
                                 b'{"x": 1234567890123456789}\n',
                                 b'{"x": 1, "x": 2}\n', b'{"x": {"y": 1, "y": 2}}\n'])
def test_truncated_nonfinite_duplicate_and_malformed_jsonl_are_refused(raw):
    with pytest.raises(candidate.SyntheticCheckpointRefusal):
        merge(((ITEM_A, 0),), new_responses=raw)


@pytest.mark.parametrize('bad', [None, False, 1, 'true'])
def test_explicit_synthetic_scope_is_required(bad):
    spec = inventory(((ITEM_A, 0),))
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='synthetic-only'):
        candidate.merge_synthetic_checkpoint(spec, original_readings=b'', original_responses=b'',
                                             added_readings=b'', added_responses=b'', synthetic_only=bad)


def test_hash_mismatch_is_checked_before_parsing_any_fragment(monkeypatch):
    spec = inventory(((ITEM_A, 0),))
    monkeypatch.setattr(candidate, '_rows', lambda _: (_ for _ in ()).throw(AssertionError('parsed')))
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='byte identity'):
        candidate.merge_synthetic_checkpoint(spec, original_readings=b'invented bytes', original_responses=b'',
                                             added_readings=b'', added_responses=b'', synthetic_only=True)


def test_mutated_assignment_inventory_is_revalidated_at_use():
    spec = inventory(((ITEM_A, 0),))
    object.__setattr__(spec, 'assignments', ((ITEM_A, 0), (ITEM_A, 0)))
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='duplicate'):
        candidate.merge_synthetic_checkpoint(spec, original_readings=b'', original_responses=b'',
                                             added_readings=b'', added_responses=b'', synthetic_only=True)


@pytest.mark.parametrize('assignments', [(), ((ITEM_A, True),), ((ITEM_A, -1),), ((ITEM_A, 20),),
                                         (('not-synthetic', 0),), ((ITEM_A, 0), (ITEM_A, 0))])
def test_bad_or_duplicate_assignment_inventory_is_rejected(assignments):
    with pytest.raises(candidate.SyntheticCheckpointRefusal):
        inventory(assignments)


def test_projection_uses_no_filesystem_or_network(monkeypatch):
    a = response(ITEM_A)
    old = jsonl(a)
    row = jsonl(reading(a))
    spec = inventory(((ITEM_A, 0),), responses=old)

    def forbidden(*_args, **_kwargs):
        raise AssertionError('filesystem or network access was attempted')

    with monkeypatch.context() as scoped:
        scoped.setattr(builtins, 'open', forbidden)
        scoped.setattr(os, 'open', forbidden)
        scoped.setattr(socket, 'socket', forbidden)
        scoped.setattr(socket, 'create_connection', forbidden)
        result = candidate.merge_synthetic_checkpoint(spec, original_readings=b'', original_responses=old,
                                                       added_readings=row, added_responses=b'', synthetic_only=True)
    assert result.responses_bytes == old and result.readings_bytes == row


def test_new_response_cannot_add_an_attempt_to_a_completed_original_row():
    first = response(ITEM_A)
    # A fabricated repair of a successful first response is not permitted even
    # if its synthetic digest is made to look like a repair of bad text.
    second = response(ITEM_A, attempt=1, text=answer('BETA'), first='SYNTH-NONJSON')
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='completed original'):
        merge(((ITEM_A, 0),), old_readings=jsonl(reading(first)), old_responses=jsonl(first),
              new_responses=jsonl(second))


def test_invalid_or_absent_attempt_fields_never_produce_a_completed_row():
    first = response(ITEM_A)
    row = reading(first)
    row['attempts'][0].pop('prompt_sha256')
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='attempt fields'):
        merge(((ITEM_A, 0),), new_readings=jsonl(row), new_responses=jsonl(first))


def test_bounds_reject_oversized_raw_fragments_before_json_parsing():
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='too large'):
        merge(((ITEM_A, 0),), new_readings=b' ' * (candidate.MAX_BYTES + 1))


def test_response_quotes_must_come_from_the_closed_invented_set():
    first = response(ITEM_A)
    altered = literal('ALPHA')
    altered['quote'] = 'SYNTH-QUOTE-ARBITRARY'
    first['text'] = json.dumps(altered, sort_keys=True, separators=(',', ':'))
    with pytest.raises(candidate.SyntheticCheckpointRefusal, match='closed synthetic'):
        merge(((ITEM_A, 0),), new_responses=jsonl(first))
