"""Stateful detail reading independent of place lookup and approval policy.

Lexers are passed in by the Korean address grammar. Every consumed detail has
an original span. Missing, parsed and unresolved fields remain distinct.
"""
from dataclasses import dataclass
from enum import Enum
import re


class FieldState(str, Enum):
    MISSING = 'missing'
    PARSED = 'parsed'
    UNRESOLVED = 'unresolved'


@dataclass(frozen=True)
class DetailToken:
    kind: str
    values: tuple
    start: int
    end: int
    text: str
    field_name: str | None = None


@dataclass(frozen=True)
class ParseIssue:
    reason: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ParsedDetails:
    tokens: tuple[DetailToken, ...]
    issues: tuple[ParseIssue, ...]
    unresolved_fields: frozenset[str]
    consumed: int
    remainder: str
    stop_reason: str

    @property
    def complete(self):
        return not self.issues and not self.unresolved_fields

    def state(self, kind):
        if kind in self.unresolved_fields or self.issues:
            return FieldState.UNRESOLVED
        return FieldState.PARSED if any(t.kind == kind for t in self.tokens) else FieldState.MISSING

    def as_units(self):
        """Compatibility view; uncertainty can never become an absent key."""
        units = {}
        for token in self.tokens:
            if token.values:
                units.setdefault(token.kind, set()).update(token.values)
        for kind in self.unresolved_fields:
            units.setdefault(kind, None)
        if not self.complete:
            units['unparsed'] = None
        return units


class DetailReader:
    def __init__(self, grammar, text, start, *, place_name='', registered=False, expected_units=None):
        self.g = grammar
        self.text = text
        self.pos = start
        self.place_name = place_name
        self.registered = registered
        self.expected = expected_units or {}
        self.tokens = []
        self.issues = []
        self.pending = set()
        self.last_detail = False
        self.stop_reason = 'end'

    def emit(self, kind, values, end, *, field_name=None):
        self.tokens.append(DetailToken(kind, tuple(values), self.pos, end, self.text[self.pos:end], field_name))
        if values:
            self.pending.difference_update((kind, 'detail'))
        self.pos = end
        self.last_detail = kind in ('층', '호', '동', '관', '건물')

    def fail(self, reason):
        self.stop_reason = 'unresolved'
        end = self.pos
        while end < len(self.text) and not self.text[end].isspace():
            end += 1
        self.issues.append(ParseIssue(reason, self.pos, end, self.text[self.pos:end]))

    def read(self):
        g = self.g
        name_building = g._BUILDING_DETAIL.fullmatch(g.compact(self.place_name))
        while self.pos < len(self.text):
            tail = self.text[self.pos:]
            postal = re.match(
                r'^' + g._ADDRESS_SEPARATORS + r'*[([{]\s*([가-힣]{2,}\d*동(?:\d+가)?)'
                r'(?:' + g._NAME_ENDING + r')?\s*(?=[,)\]}])', tail,
            )
            if postal:
                self.emit('모호동', (postal[1],), self.pos + postal.end())
                continue
            separators = re.match(g._ADDRESS_SEPARATORS + '+', tail)
            separated = bool(separators)
            if separators:
                self.pos += separators.end()
                tail = self.text[self.pos:]
                if not tail:
                    break
            name = g._known_name_match(self.place_name, tail)
            if name and not (self.registered and name_building):
                if name_building:
                    key, value = g._building_unit(name_building)
                    if value in self.expected.get(key, set()):
                        self.emit(key, (value,), self.pos + name.end())
                        continue
                self.emit('name', (), self.pos + name.end())
                continue
            if tail.startswith('-') and g._known_name_match(self.place_name, tail[1:].lstrip()):
                # A separator leading directly to the known place is not an
                # unfinished range. Unknown endpoints still carry an issue.
                self.emit('separator', (), self.pos + 1)
                continue
            if self.tokens and g._RANGE_CONTINUATION.match(tail):
                self.fail('unresolved_range')
                break
            # Particles are transitions only after an actual detail. They do
            # not erase the detail following them or start a new prose scope.
            if self.last_detail:
                particle = re.match(g._NAME_ENDING + r'|인', tail)
                if particle:
                    rest = tail[particle.end():]
                    if not rest or not re.match(r'[a-z0-9가-힣]', rest) or g._detail_lexeme(rest):
                        self.pos += particle.end()
                        continue
            owner = re.match(r'(?:매장|가게|점포)(?:은|는|이|가)\s*', tail) if not name else None
            if owner:
                self.emit('owner', (), self.pos + owner.end())
                continue
            unit = g._read_numeric_detail(tail)
            if unit:
                kind, values, length, issue = unit
                if issue:
                    self.fail(issue)
                    break
                self.emit(kind, values, self.pos + length)
                continue
            building = g._BUILDING_DETAIL.match(tail)
            if building:
                key, value = g._building_unit(building)
                self.emit(key, (value,), self.pos + building.end())
                continue
            label = re.match(g._DETAIL_LABEL, tail)
            if label and label[1] == '호수' and not g._room_field_value(tail[label.end():]):
                label = None
            if label:
                kind = {'층수': '층', '호수': '호'}.get(label[1], 'detail')
                self.pending.add(kind)
                self.emit('field', (), self.pos + label.end(), field_name=kind)
                continue
            phone = re.match(
                r'(?:(?:전화번호|전화|연락처|tel)\s*[:：]?\s*)?'
                r'\(?0\d{1,3}\)?[\s-]+\d{3,4}[\s-]+\d{4}(?!\d)', tail,
            )
            if phone:
                self.emit('phone', (), self.pos + phone.end())
                continue
            if not self.registered and g._facility_scope(tail):
                self.stop_reason = 'facility_prose'
                break
            if g._unknown_detail(tail):
                self.fail('unrecognized_detail')
                break
            qualifier = re.match(r'[가-힣a-z0-9]+(?:읍|면|리|가)(?=$|[\s,()[\]])', tail)
            if qualifier:
                self.emit('locality', (), self.pos + qualifier.end())
                continue
            if self.last_detail and not separated and re.match(r'[a-z0-9가-힣]', tail):
                self.fail('unrecognized_attached_suffix')
            elif self.registered and g._unknown_detail(tail, search=True):
                self.fail('unrecognized_registered_detail')
            else:
                self.stop_reason = 'ordinary_prose'
            break
        if self.pending:
            self.fail('unresolved_field')
        return ParsedDetails(tuple(self.tokens), tuple(self.issues), frozenset(self.pending), self.pos, self.text[self.pos:], self.stop_reason)
