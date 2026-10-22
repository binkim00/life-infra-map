"""Pure place identity parsing: normalization, detail reading, then comparison.

This module has no Django, database, HTTP or review-state dependencies.
Regexes identify lexical forms; the reader retains spans and unresolved state.
"""
import re

from .address_details import DetailReader


def _facility_scope(text):
    return bool(re.match(r'(?:화장실|주차장|엘리베이터)(?:은|는|이|가|의|\s*위치)', text))

def _read_numeric_detail(text):
    """Lex one full numeric value/range; never predict the following word."""
    endpoints = re.match(
        r'(?:(지하|지상|b)\s*)?(?:제\s*)?(\d+)\s*(' + _UNIT_TOKEN + r')'
        r'\s*[~～〜-]\s*(?:(지하|지상|b)\s*)?(?:제\s*)?(\d+)\s*(' + _UNIT_TOKEN + r')', text,
    )
    if endpoints:
        level, first, kind, last_level, last, last_kind = endpoints.groups()
        kind, last_kind = ({'f': '층', '호실': '호'}.get(k, k) for k in (kind, last_kind))
        if kind != last_kind or (level in ('지하', 'b')) != (last_level in ('지하', 'b')):
            return kind, (), endpoints.end(), 'mixed_range_units'
        length = endpoints.end()
    else:
        match = re.match(
            r'(?:(지하|지상|b)\s*)?(?:제\s*)?(\d+)(?:\s*[~～〜-]\s*(\d+))?\s*('
            + _UNIT_TOKEN + r')|b\s*(\d+)(?![a-z0-9]|\s*(?:동|관|호))', text,
        )
        if not match:
            return None
        level, first, last, kind, bare = match.groups()
        if bare:
            level, first, kind = 'b', bare, '층'
        kind = {'f': '층', '호실': '호'}.get(kind, kind)
        length = match.end()
    first = first.lstrip('0') or '0'
    last = (last.lstrip('0') or '0') if last is not None else None
    if len(first) > 6 or (last is not None and (len(last) > 6 or not 0 <= int(last) - int(first) <= 100)):
        return kind, (), length, 'unsupported_range_size'
    values = range(int(first), int(last) + 1) if last is not None else (int(first),)
    return kind, tuple((level in ('지하', 'b'), str(n)) for n in values), length, None


def _unknown_detail(text, *, search=False):
    pattern = (
        r'(?:(?:지하|지상|제)\s*)?'
        r'[a-z0-9영공일이삼사오육칠팔구십백천미정확인한두세네?~～〜-]+\s*(?:층|호(?!점|선)|동|관)'
    )
    if search:
        return bool(re.search(r'(?<![a-z0-9가-힣])' + pattern, text) or re.search(r'(?:층|호)(?=$|' + _ADDRESS_SEPARATORS + ')', text))
    return bool(re.match(pattern, text) or re.match(_UNPARSED_UNIT, text))


def _room_field_value(text):
    # A lake predicate is prose. A colon, numeric value or uncertainty marker
    # makes this the room-number field. The field lexer itself has no whitelist.
    value = text.lstrip()
    if not value or value.startswith((':', '：')) or re.match(r'(?:제\s*)?\d', value) or _read_numeric_detail(value):
        return True
    # Unknown predicates are a lexical category, independent of spacing and
    # of which particular field/candidate scanner encountered the value.
    word = compact(value)
    return word.startswith(('미', '불', '부정', '확인', '정보', '없', '알수없', '모름', '모르')) or value.startswith(('?', '~'))


def _detail_lexeme(text):
    return bool(_read_numeric_detail(text) or _BUILDING_DETAIL.match(text) or re.match(_DETAIL_LABEL, text) or _unknown_detail(text))


def _branch_numbers(text):
    return {n.lstrip('0') or '0' for n in re.findall(r'(?<!\d)(?:제\s*)?(\d+)\s*호점', _address_text(text))}


    # Assigned below after the vocabulary is defined.


def _known_name_match(name, text):
    pattern = _place_name_pattern(name)
    return re.match(pattern + r"[\s'\"‘’“”)\]}]*(?:" + _NAME_ENDING + r')?' + _DETAIL_BOUNDARY, text) if pattern else None


def parse_address_details(text, start=0, *, place_name='', registered=False, expected_units=None):
    """Parse normalized text, retaining normalized source spans and issues."""
    return DetailReader(_KoreanDetailGrammar, text, start, place_name=place_name,
                        registered=registered, expected_units=expected_units).read()
def compact(value):
    return re.sub(r"[^a-z0-9가-힣]", "", str(value).lower())

def _place_name_pattern(name):
    return r"[\W_]*".join(re.escape(char) for char in compact(name))

_NAME_ENDING = (
    r"(?:입니다|이에요|예요|이네요|이죠|이고|이며|이었다|이었어요|이라는|이라서"
    r"|(?:에서|으로|에게|에|와|과|로)(?:는|도|만)?|은|는|이|가|을|를|의|도|만)"
)

_UNIT_TOKEN = r"(?:층|호(?!점|선)(?:실)?|f)"
# Adjacency is only lexical; the reader validates every complete next token.
_DETAIL_BOUNDARY = r"(?=$|[^a-z0-9가-힣]|\d|지하|지상|b\s*\d|제\s*\d)"




_ADDRESS_NUMBER = (
    r"(?P<main>\d+)(?:\s*-\s*(?P<sub>\d+))?"
    r"(?!\d|\s*[-/]\s*\d|\s*(?:번\s*)?길|(?:층|호|동)|\s+(?:층|호|동)"
    r"(?=$|[^a-z0-9가-힣]|실|인(?:데|지)?(?![가-힣])|까지|부터|"
    + _NAME_ENDING + r"(?![가-힣])))"
)

_ROAD_ADDRESS = re.compile(
    r"(?<![a-zA-Z0-9가-힣])(?P<name>[a-zA-Z0-9가-힣]+(?:대로|로|길))\s*"
    + _ADDRESS_NUMBER
)

_LOT_ADDRESS = re.compile(
    # Require a named locality before its suffix: parking capacity "143면
    # 10분당" and apartment "101동 2층" are not additional lot addresses.
    r"(?<![a-zA-Z0-9가-힣])(?P<name>[가-힣0-9]*[가-힣][가-힣0-9]*(?:읍|면|동|리|가))\s*"
    r"(?P<mountain>산\s*)?" + _ADDRESS_NUMBER
)

_BUILDING_WINGS = r"본관|별관|신관|구관|동관|서관|남관|북관"

_ADDRESS_SEPARATORS = r"""[\s,()[\]{}:：/|·.!?;'"‘’“”]"""

_BUILDING_DETAIL = re.compile(
    r"(?:(?P<wing>" + _BUILDING_WINGS + r")"
    r"|(?:제\s*)?(?P<block>[가-힣a-z0-9]+)\s*(?P<kind>빌딩|타워|센터|상가|동|관))"
    r"(?=$|" + _ADDRESS_SEPARATORS + r"|\d|지하|지상|제|b\s*\d|"
    + _NAME_ENDING + _DETAIL_BOUNDARY + r")"
)

_SPACED_WINGS = "|".join(r"\s*".join(wing) for wing in _BUILDING_WINGS.split("|"))

_TITLE_NARRATIVE_WORDS = re.compile(
    r"(?<![a-z0-9가-힣])(?:감동|활동)(?![a-z0-9가-힣])"
)

_DETAIL_LABEL = r"(층수|호수|상세주소)(?:은|는|이|가)?"

_UNPARSED_UNIT = (
    r"[가-힣a-z0-9?~～〜-]*(?:층|호(?!점|선))"
    r"(?=$|" + _ADDRESS_SEPARATORS + r"|" + _NAME_ENDING + r"(?![a-z0-9가-힣]))"
)

_TITLE_DETAIL_START = re.compile(
    r"(?<![a-z0-9가-힣])(?:" + _BUILDING_DETAIL.pattern
    + r"|" + _DETAIL_LABEL
    + r"|(?:(?:지하|지상|b)\s*)?(?:제\s*)?\d+\s*" + _UNIT_TOKEN
    + r"|b\s*\d+(?![a-z0-9]))"
    r"|(?<![a-z0-9가-힣])" + _UNPARSED_UNIT
)

_TITLE_FLOOR_CORE = (
    r"(?:(?:(?:지하|지상|b)\s*)?(?:제\s*)?\d+\s*(?:층|f)?\s*[~～〜-]\s*"
    r"(?:(?:지하|지상|b)\s*)?(?:제\s*)?\d+\s*(?:층|f)"
    r"|(?:(?:지하|지상|b)\s*)?(?:제\s*)?\d+\s*(?:층|f)"
    r"|b\s*\d+)(?![a-z0-9])"
)

_TITLE_FLOOR = r"(?<![a-z0-9가-힣])" + _TITLE_FLOOR_CORE

_ADDRESS_BRACKETS = str.maketrans({
    **{char: "(" for char in "（［｛【〔〈《「『"},
    **{char: ")" for char in "）］｝】〕〉》」』"},
})

_RANGE_CONTINUATION = re.compile(
    r"[~～〜-]"
    r"|부터|내지"
    r"|(?:및|그리고|또는|에서)\s*(?=(?:지하|지상|b)?\s*\d+\s*(?:층|호(?!점|선)|f))"
)

_PROVINCE_ALIASES = {
    alias: name
    for name, aliases in (
        ("서울", ("서울", "서울시", "서울특별시")),
        ("부산", ("부산", "부산시", "부산광역시")),
        ("대구", ("대구", "대구시", "대구광역시")),
        ("인천", ("인천", "인천시", "인천광역시")),
        ("광주", ("광주", "광주광역시")),
        ("대전", ("대전", "대전시", "대전광역시")),
        ("울산", ("울산", "울산시", "울산광역시")),
        ("세종", ("세종", "세종시", "세종특별자치시")),
        ("경기", ("경기", "경기도")),
        ("강원", ("강원", "강원도", "강원특별자치도")),
        ("충북", ("충북", "충청북도")),
        ("충남", ("충남", "충청남도")),
        ("전북", ("전북", "전라북도", "전북특별자치도")),
        ("전남", ("전남", "전라남도")),
        ("경북", ("경북", "경상북도")),
        ("경남", ("경남", "경상남도")),
        ("제주", ("제주", "제주도", "제주특별자치도")),
    )
    for alias in aliases
}

def _address_text(text):
    text = str(text or "").lower()
    text = text.translate(_ADDRESS_BRACKETS)
    text = text.translate(str.maketrans({c: "-" for c in "‐‑–—−"}))
    # Join only road-name fragments, never the building number and floor/phone.
    text = re.sub(r"(?<=[가-힣0-9])\s+(?=(?:대로|로|길)(?:\s|\d))", "", text)
    return re.sub(r"(?<=[가-힣0-9])\s+(?=\d+(?:번)?길)", "", text)

def _address_location(text, start):
    """Administrative qualifiers immediately before this address, not its title."""
    # Address blocks may wrap or parenthesize a neighborhood. These separators
    # must not erase a conflicting city/district immediately before the road.
    location = {}
    tokens = [token for token in re.split(r"[\s,()[\]{}:：/|·.!?;]+", text[:start]) if token]
    for token in reversed(tokens):
        if token in {"주소", "도로명주소", "도로명", "지번주소", "지번", "소재지", "위치", "address"}:
            continue
        if token in _PROVINCE_ALIASES:
            level, value = "province", _PROVINCE_ALIASES[token]
        elif re.fullmatch(r"[가-힣0-9]+[시군구읍면동리가]", token):
            level = (
                "municipality" if token.endswith(("시", "군")) else
                "district" if token.endswith("구") else
                "town" if token.endswith(("읍", "면")) else "neighborhood"
            )
            value = token
        else:
            break
        # Repeated levels are ambiguous, rather than evidence of equivalence.
        if level in location and location[level] != value:
            location[level] = None
        else:
            location[level] = value
    return location

def _address_number(match, kind):
    main = match["main"].lstrip("0") or "0"
    sub = (match["sub"] or "").lstrip("0")
    if kind == "road" and match["sub"] is not None and not sub:
        sub = "0"
    return main, sub, bool(match.groupdict().get("mountain"))

def _building_unit(building):
    key = building["kind"] or "관"
    value = building["wing"] or building["block"]
    if key in ("빌딩", "타워", "센터", "상가"):
        value += key
        key = "건물"
    if value.isdigit():
        value = value.lstrip("0") or "0"
    if key == "관" and value + "관" in _BUILDING_WINGS.split("|"):
        value += "관"
    return key, value

def _explicit_neighborhoods(text):
    return {
        location["neighborhood"]
        for pattern in (_ROAD_ADDRESS, _LOT_ADDRESS)
        for match in _address_matches(pattern, text)
        for location in [_address_location(text, match.start())]
        if location.get("neighborhood")
    }

def _resolve_dong_units(units, neighborhoods, building_dongs=()):
    """A parenthesis is not proof of an administrative or building role."""
    result = {key: None if value is None else set(value) for key, value in units.items()}
    for label in result.pop("모호동", set()):
        administrative = label in neighborhoods
        building = label[:-1] in building_dongs
        if administrative == building:
            result["unparsed"] = None
        else:
            key, value = ("행정동", label) if administrative else ("동", label[:-1])
            result.setdefault(key, set()).add(value)
    return result

def _address_units(text, end, *, place_name="", registered=False, expected_units=None):
    return parse_address_details(text, end, place_name=place_name, registered=registered, expected_units=expected_units).as_units()


def _address_matches(pattern, text):
    """Exclude quantity expressions such as '추가로 2잔' and '우리가 2명'."""
    for match in pattern.finditer(text):
        if re.match(
            r"\s*(?:시간|차례|잔|명|개|분|원|회|대|면|번)"
            r"(?:(?:당|씩|을|를|이|가|은|는|만|도|의)(?![가-힣])|(?=$|[^가-힣]))",
            text[match.end():],
        ):
            continue
        yield match

def matching_address(address, prose, *, place_name=""):
    """Match an explicit address, never infer a move or convert road/lot forms.

    This is only an address gate. Place/branch name and claim attribution still
    have to pass the independent checks in assess_content().
    """
    address, prose = _address_text(address), _address_text(prose)
    neighborhoods = _explicit_neighborhoods(address) | _explicit_neighborhoods(prose)
    candidates = [
        match for pattern in (_ROAD_ADDRESS, _LOT_ADDRESS)
        for match in _address_matches(pattern, prose)
    ]
    for kind, pattern in (("road", _ROAD_ADDRESS), ("lot", _LOT_ADDRESS)):
        for expected in _address_matches(pattern, address):
            name = r"\s*".join(re.escape(c) for c in expected["name"])
            separator = r"\s*"
            mountain = r"(?P<mountain>산\s*)?" if kind == "lot" else ""
            mention_pattern = re.compile(
                r"(?<![a-zA-Z0-9가-힣])" + name + separator + mountain + _ADDRESS_NUMBER,
            )
            mentions = list(_address_matches(mention_pattern, prose))
            if not mentions:
                continue
            # Inspect both address forms: a move can be road-to-lot or vice
            # versa. No equivalence between the two forms is inferred here.
            # A flexible expected-name match can contain a whitespace-split
            # candidate, so compare spans rather than partial parsed names.
            if any(
                not any(m.start() <= other.start() and other.end() <= m.end() for m in mentions)
                for other in candidates
            ):
                continue
            expected_number = _address_number(expected, kind)
            location = _address_location(address, expected.start())
            # Multiple numbers on the same road/parcel name may be old/new
            # addresses or different branches. Leave them for context review.
            if any(_address_number(m, kind) != expected_number for m in mentions):
                continue
            locations = [_address_location(prose, m.start()) for m in mentions]
            if any(
                value is None or (level in location and location[level] != value)
                for found in locations for level, value in found.items()
            ):
                continue
            if any(value is None for value in location.values()):
                continue
            if (
                location.get("province") in {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}
                and any(found.get("municipality", "").endswith("시") for found in locations)
            ):
                continue
            units = _address_units(address, expected.end(), place_name=place_name, registered=True)
            units = _resolve_dong_units(units, neighborhoods, units.get("동", set()))
            if location.get("neighborhood"):
                units.setdefault("행정동", set()).add(location["neighborhood"])
            if any(value is None for value in units.values()) or any(
                len(values) > 1 for unit, values in units.items() if unit in ("동", "관", "건물", "행정동")
            ):
                continue
            found_units = [
                _resolve_dong_units(
                    _address_units(prose, m.end(), place_name=place_name, expected_units=units),
                    neighborhoods, units.get("동", set()),
                )
                for m in mentions
            ]
            for found, found_location in zip(found_units, locations):
                if found_location.get("neighborhood"):
                    found.setdefault("행정동", set()).add(found_location["neighborhood"])
            if any(len(found.get("행정동", set())) > 1 for found in found_units):
                continue
            # Any explicit contradiction or parse failure vetoes the quote.
            # Missing components in a repeated address are neutral, but one
            # coherent mention must verify ALL registered details; never join
            # incomplete mentions into an invented complete address.
            if any(
                value is None or (unit in units and not value.issubset(units[unit]))
                for found in found_units for unit, value in found.items()
            ):
                continue
            if not any(all(
                found.get(unit) == value for unit, value in units.items() if unit != "행정동"
            ) for found in found_units):
                continue
            if any(
                first[unit] != second[unit]
                for first in found_units for second in found_units
                for unit in (first.keys() & second.keys()) - units.keys()
            ):
                continue
            return True
    return False

def unambiguous_full_name(name, text, *, allowed_units=None):
    """Validate each full-name mention using complete detail tokens, not prefixes."""
    text = _address_text(text)
    pattern = _place_name_pattern(name)
    if not pattern:
        return False
    matches = list(re.finditer(pattern, text))
    registered_branches = _branch_numbers(name)
    for match in matches:
        if match.start() and re.match(r"[a-z0-9가-힣]", text[match.start() - 1]):
            return False
        tail = text[match.end():]
        branch = re.match(r"[\W_]*(?:제\s*)?(\d+)\s*호점", tail)
        if branch:
            if (branch[1].lstrip("0") or "0") not in registered_branches:
                return False
            tail = tail[branch.end():]
        if re.match(r"[\W_]*분점", tail):
            return False
        wing = re.match(r"[\W_]*(" + _SPACED_WINGS + ")", tail)
        if wing:
            if compact(wing[1]) not in (allowed_units or {}).get("관", set()):
                return False
            tail = tail[wing.end():]
            if re.match(r"[\W_]*(?:(?:제\s*)?\d+\s*호점|분점|" + _SPACED_WINGS + ")", tail):
                return False
        if not re.match(r"[a-z0-9가-힣]", tail):
            continue
        ending = re.match(_NAME_ENDING, tail)
        if ending:
            tail = tail[ending.end():]
            if not re.match(r"[a-z0-9가-힣]", tail):
                continue
        parsed = parse_address_details(tail, place_name=name, expected_units=allowed_units)
        if not parsed.complete or not any(t.kind in ("층", "호") for t in parsed.tokens):
            return False
    return bool(matches)


def _ordinal_branch_conflict(name, text):
    """A room/rail exception must not erase another branch's identity."""
    remaining = re.sub(_place_name_pattern(name), " ", _address_text(text))
    return not _branch_numbers(remaining).issubset(_branch_numbers(name))

def _registered_address_units(place, prose):
    address = _address_text(place.address)
    neighborhoods = _explicit_neighborhoods(address) | _explicit_neighborhoods(_address_text(prose))
    registered = []
    for pattern in (_ROAD_ADDRESS, _LOT_ADDRESS):
        for match in _address_matches(pattern, address):
            details = _address_units(address, match.end(), place_name=place.name, registered=True)
            details = _resolve_dong_units(details, neighborhoods, details.get("동", set()))
            location = _address_location(address, match.start())
            if location.get("neighborhood"):
                details.setdefault("행정동", set()).add(location["neighborhood"])
            if any(value is None for value in details.values()):
                return None
            registered.append(details)
    return registered[0] if len(registered) == 1 else None

def _title_address_text(place, text, *, neighborhoods=()):
    """Veto explicit address conflicts, then mask only validated address spans.

    A title may omit floors/rooms; those must already be verified in prose.
    Do not mistake a lot locality for an additional building block.
    """
    address = _address_text(place.address)
    valid_spans = []
    for kind, pattern in (("road", _ROAD_ADDRESS), ("lot", _LOT_ADDRESS)):
        for expected in _address_matches(pattern, address):
            name = r"\s*".join(re.escape(c) for c in expected["name"])
            mountain = r"(?P<mountain>산\s*)?" if kind == "lot" else ""
            mentions = re.compile(r"(?<![a-z0-9가-힣])" + name + r"\s*" + mountain + _ADDRESS_NUMBER)
            location = _address_location(address, expected.start())
            for mention in _address_matches(mentions, text):
                found = _address_location(text, mention.start())
                if _address_number(mention, kind) != _address_number(expected, kind) or any(
                    value is None or (level in location and location[level] != value)
                    for level, value in found.items()
                ):
                    continue
                if neighborhoods and found.get("neighborhood") and found["neighborhood"] not in neighborhoods:
                    continue
                if (
                    location.get("province") in {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}
                    and found.get("municipality", "").endswith("시")
                ):
                    continue
                valid_spans.append(mention.span())
                if found.get("neighborhood"):
                    # Only a typed prefix of this validated address is
                    # administrative; a later parenthesized dong stays ambiguous.
                    prefix = re.search(
                        r"(?<![a-z0-9가-힣])(" + re.escape(found["neighborhood"]) + r")"
                        + _ADDRESS_SEPARATORS + r"*$", text[:mention.start()],
                    )
                    if prefix:
                        valid_spans.append(prefix.span(1))
    if any(
        not any(start <= candidate.start() and candidate.end() <= end for start, end in valid_spans)
        for pattern in (_ROAD_ADDRESS, _LOT_ADDRESS) for candidate in _address_matches(pattern, text)
    ):
        return None
    for start, end in valid_spans:
        text = text[:start] + " " * (end - start) + text[end:]
    return text

def _mask_title_restroom_floors(text):
    """Exclude only explicit, parsed restroom floors, retaining other details."""
    patterns = (
        r"(?P<floor>" + _TITLE_FLOOR_CORE + r")(?:의|에(?:\s*있는)?)?\s*화장실"
        r"(?=$|" + _ADDRESS_SEPARATORS + r"|" + _NAME_ENDING + r"(?![a-z0-9가-힣]))",
        r"(?<![a-z0-9가-힣])화장실\s*(?:(?:은|는|이|가)|(?:의\s*)?위치(?:는)?\s*[:：]?)?"
        r"\s*(?P<floor>" + _TITLE_FLOOR_CORE + r")",
    )
    unparsed = False
    for pattern in patterns:
        def mask(match):
            nonlocal unparsed
            start, end = match.span("floor")
            if start == match.start() and start and re.match(r"[a-z0-9가-힣]", text[start - 1]):
                prefix = text[:start]
                if not any(
                    building.end() == start and (
                        not building.start() or not re.match(r"[a-z0-9가-힣]", prefix[building.start() - 1])
                    ) for building in _BUILDING_DETAIL.finditer(prefix)
                ):
                    unparsed = True
                    return match[0]
            # A range/unknown continuation must retain its unparsed state.
            following = re.sub(r"^" + _ADDRESS_SEPARATORS + r"+", "", text[end:])
            if re.search(r"[~～〜-]\s*$", text[:start]) or _RANGE_CONTINUATION.match(following):
                unparsed = True
                return match[0]
            units = _address_units(match["floor"], 0)
            if set(units) != {"층"} or units["층"] is None:
                unparsed = True
                return match[0]
            offset = start - match.start()
            return match[0][:offset] + " " * (end - start) + match[0][offset + end - start:]
        text = re.sub(pattern, mask, text)
    return None if unparsed else text

def title_building_matches(place, title, *, registered_units=None, prose=""):
    """Use the same detail parser at every explicit title component."""
    registered = registered_units if registered_units is not None else _registered_address_units(place, "")
    if registered is None:
        return False
    neighborhoods = registered.get("행정동", set()) | _explicit_neighborhoods(_address_text(prose))
    text = re.sub(_place_name_pattern(place.name), lambda m: " " * len(m[0]), _address_text(title))
    text = _title_address_text(place, text, neighborhoods=neighborhoods)
    if text is None:
        return False
    text = _mask_title_restroom_floors(text)
    if text is None:
        return False
    if _ordinal_branch_conflict(place.name, text) or re.search(r"(?<![a-z0-9가-힣])분점", text):
        return False
    # Ordinary narrative words are not arbitrary one-letter Korean blocks.
    # Keep them structural if immediately followed by an explicit unit.
    def mask_narrative(match):
        if re.match(r"\s*(?:제\s*)?\d+\s*(?:층|호)", text[match.end():]):
            return match[0]
        return " " * len(match[0])
    text = _TITLE_NARRATIVE_WORDS.sub(mask_narrative, text)
    for candidate in _TITLE_DETAIL_START.finditer(text):
        start = candidate.start()
        opening = re.search(r"[([{][\s([{]*$", text[:start])
        if opening:
            start = opening.start()
        found = _resolve_dong_units(_address_units(text, start), neighborhoods, registered.get("동", set()))
        if any(value is None for value in found.values()):
            return False
        for unit in ("동", "관", "건물", "층", "호", "행정동"):
            values = found.get(unit, set())
            if unit == "동":
                values = {v for v in values if v + "동" not in neighborhoods or v in registered.get("동", set())}
            if unit in ("층", "호") and unit not in registered:
                continue
            allowed = neighborhoods if unit == "행정동" else registered.get(unit, set())
            if not values.issubset(allowed):
                return False
    return True


class _KoreanDetailGrammar:
    """Explicit lexical vocabulary for the location-free detail reader."""
    _ADDRESS_SEPARATORS = _ADDRESS_SEPARATORS
    _NAME_ENDING = _NAME_ENDING
    _BUILDING_DETAIL = _BUILDING_DETAIL
    _RANGE_CONTINUATION = _RANGE_CONTINUATION
    _DETAIL_LABEL = _DETAIL_LABEL
    compact = staticmethod(compact)
    _place_name_pattern = staticmethod(_place_name_pattern)
    _known_name_match = staticmethod(_known_name_match)
    _building_unit = staticmethod(_building_unit)
    _read_numeric_detail = staticmethod(_read_numeric_detail)
    _unknown_detail = staticmethod(_unknown_detail)
    _room_field_value = staticmethod(_room_field_value)
    _detail_lexeme = staticmethod(_detail_lexeme)
    _facility_scope = staticmethod(_facility_scope)
