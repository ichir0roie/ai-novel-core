from ai.instructions.event_writing import CHARACTER_TEXT_UPDATE_INSTRUCTION, EVENT_PROGRESSION_INSTRUCTION
from ai.instructions.naming import CHARACTER_NAMING_INSTRUCTION


def test_event_progression_instruction_warns_against_reusing_wording():
    assert "同じ形容表現を繰り返し出来事の軸に据えない" in EVENT_PROGRESSION_INSTRUCTION


def test_character_text_update_instruction_warns_against_reusing_wording():
    assert "繰り返さない" in CHARACTER_TEXT_UPDATE_INSTRUCTION


def test_character_naming_instruction_refers_to_the_passed_name_list():
    assert "既にいる人物・対象の名" in CHARACTER_NAMING_INSTRUCTION
