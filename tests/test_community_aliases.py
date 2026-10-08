import json

from src.core.community_aliases import AliasDictionary, load_aliases, reset_override, save_override


def test_builtin_dictionary_loads():
    dictionary = load_aliases()
    assert dictionary.entry_count > 30


def test_slang_resolution_for_valkyrie_and_bloodhound():
    dictionary = load_aliases()
    valk_terms = dictionary.aliases_for_target("瓦尔基里")
    assert "挖机" in valk_terms and "瓦鸡" in valk_terms and "Valkyrie" in valk_terms
    bh_terms = dictionary.aliases_for_target("Bloodhound")
    assert "狗子" in bh_terms and "寻血猎犬" in bh_terms


def test_target_matching_is_bidirectional_and_case_insensitive():
    dictionary = load_aliases()
    assert "挖机" in dictionary.aliases_for_target("valkyrie")
    assert "挖机" in dictionary.aliases_for_target("瓦尔基里喷射套件")  # compound target
    assert dictionary.aliases_for_target("") == []
    assert dictionary.aliases_for_target("不存在的传奇") == []


def test_weapon_aliases():
    dictionary = load_aliases()
    assert "r99" in dictionary.aliases_for_target("R-99")
    assert "转换者" in dictionary.aliases_for_target("Alternator")


def test_prompt_table_contains_slang():
    table = load_aliases().prompt_table()
    assert "挖机" in table and "瓦尔基里" in table


def test_override_roundtrip(tmp_path):
    data = {"legends": {"TestLegend": {"zh": "测试传奇", "aliases": ["测测"]}}}
    dictionary = save_override(tmp_path, json.dumps(data, ensure_ascii=False))
    assert set(dictionary.aliases_for_target("测试传奇")) == {"测测", "测试传奇", "TestLegend"}
    loaded = load_aliases(tmp_path)
    assert loaded.aliases_for_target("TestLegend")
    reset_override(tmp_path)
    assert load_aliases(tmp_path).entry_count > 30  # falls back to builtin


def test_save_override_rejects_invalid_json(tmp_path):
    try:
        save_override(tmp_path, "{bad json")
        assert False, "should raise"
    except json.JSONDecodeError:
        pass
    try:
        save_override(tmp_path, '{"other": {}}')
        assert False, "should raise"
    except ValueError:
        pass
