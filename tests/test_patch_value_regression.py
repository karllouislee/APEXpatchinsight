from pydantic import TypeAdapter
from src.core.models import PatchChange


def test_text_values_preserved():
    adapter = TypeAdapter(list[PatchChange])
    changes = adapter.validate_python([{'target': 'Bloodhound', 'summary': 'Changed',
        'exact_values': ['2 fewer jammers', '10 seconds']}])
    assert [v.raw_text for v in changes[0].exact_values] == ['2 fewer jammers', '10 seconds']
    assert all(v.before is None and v.after is None for v in changes[0].exact_values)
    assert adapter.validate_json(adapter.dump_json(changes)) == changes


def test_mixed_values_keep_structured_numbers():
    change = PatchChange(target='x', summary='x', exact_values=[
        'increases the maximum number allowed on the field by one',
        {'before': 11, 'after': 12}])
    assert change.exact_values[0].raw_text.endswith('by one')
    assert change.exact_values[0].after is None
    assert change.exact_values[1].before == '11'
    assert change.exact_values[1].after == '12'


def test_invalid_value_is_not_silently_discarded():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PatchChange(target='x', summary='x', exact_values=[123])


def test_toolbar_clearance_css():
    import re
    from src.ui.theme import CUSTOM_CSS
    rule = re.search(r'\.block-container\s*\{([^}]+)', CUSTOM_CSS).group(1)
    top = float(re.search(r'padding-top:\s*([\d.]+)rem', rule).group(1))
    assert top >= 4.5
