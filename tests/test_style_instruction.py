import pytest

from ai.instructions import style


def test_text_joins_base_and_extra():
    instruction = style.StyleInstruction(base="土台", extra="好み")
    assert instruction.text == "土台\n好み"


def test_text_is_base_only_while_extra_is_empty():
    assert style.StyleInstruction(base="土台").text == "土台"


def test_text_is_empty_without_both():
    assert style.StyleInstruction().text == ""


@pytest.mark.parametrize("target", ["episode", "event_novel", "story", "event", "idea"])
def test_style_instruction_has_shared_and_own_base(target):
    text = style.style_instruction(target)
    assert style.SHARED_STYLE_BASE.strip() in text
    assert style.STYLE_BASES[target] in text


@pytest.mark.parametrize("target", ["episode", "event_novel", "story", "event", "idea"])
def test_style_instruction_appends_the_shared_extra_from_the_caller(target):
    """世界の舞台設定・既存の話から抽出した文体の癖のような世界ごとの好みは、定数ではなく呼び出し側から渡す。"""
    text = style.style_instruction(target, shared_extra="この世界だけの舞台設定")
    assert "この世界だけの舞台設定" in text


def test_style_instruction_appends_the_target_extra_from_the_caller():
    text = style.style_instruction("episode", extra="この話だけの文体の癖")
    assert "この話だけの文体の癖" in text
    assert "この話だけの文体の癖" not in style.style_instruction("event")


def test_style_instruction_needs_no_extra_to_work_standalone():
    """コアだけでも(親リポジトリ側の値を渡さなくても)成り立つ既定値であること。"""
    text = style.style_instruction("episode")
    assert style.SHARED_STYLE_BASE.strip() in text
    assert style.EPISODE_STYLE_BASE in text


def test_style_instruction_rejects_unknown_target():
    with pytest.raises(ValueError):
        style.style_instruction("character")


def test_episode_style_states_the_line_break_rule():
    base = style.EPISODE_STYLE_BASE
    assert "地の文は一文ごとに改行する。" in base
    assert "空行は、話し手や流れが変わるところにだけ一つ置き" in base
    assert "場面が変わる(場所・時間・書く対象が変わる)ところにだけ、「◇」だけの行を置く。" in base
    assert "孤立させた一行" not in base


def test_layout_puts_each_narration_sentence_on_its_own_line():
    assert style.layout_novel_text("扉が開いた。ミレアが入ってきた。") == "扉が開いた。\nミレアが入ってきた。"


def test_layout_keeps_a_quote_on_one_line():
    text = "「知っている。だから、変える」カシルは言った。「今度こそ」"
    assert style.layout_novel_text(text) == "「知っている。だから、変える」カシルは言った。\n「今度こそ」"


def test_layout_does_not_split_repeated_marks():
    assert style.layout_novel_text("本当に！？そう。") == "本当に！？\nそう。"


def test_layout_turns_half_width_marks_into_full_width():
    assert style.layout_novel_text("「ノア! こっち!」「なに?」") == "「ノア！こっち！」「なに？」"


def test_layout_splits_sentences_at_half_width_marks():
    assert style.layout_novel_text("本当に!?そう。") == "本当に！？\nそう。"


def test_layout_turns_the_scene_break_into_two_blank_lines():
    text = "一つ目。\n\n◇\n\n二つ目。"
    assert style.layout_novel_text(text) == "一つ目。\n\n\n二つ目。"


def test_layout_keeps_one_blank_line_and_collapses_longer_runs_into_a_scene_break():
    text = "一つ目。\n\n二つ目。\n\n\n\n\n三つ目。"
    assert style.layout_novel_text(text) == "一つ目。\n\n二つ目。\n\n\n三つ目。"


def test_layout_wraps_a_long_quote_at_a_sentence_end():
    first = "「" + "あ" * 30 + "。"
    second = "い" * 30 + "。」"
    assert style.layout_novel_text(first + second) == first + "\n" + second


def test_layout_wraps_a_long_sentence_at_a_comma():
    first = "う" * 30 + "、"
    second = "え" * 30 + "。"
    assert style.layout_novel_text(first + second) == first + "\n" + second


def test_layout_keeps_a_long_sentence_without_breaks():
    text = "お" * 60 + "。"
    assert style.layout_novel_text(text) == text


def test_layout_rewraps_wrapped_lines_the_same_way():
    wrapped = "「" + "あ" * 30 + "。\n" + "い" * 30 + "。」\n" + "う" * 30 + "、\n" + "え" * 30 + "。"
    assert style.layout_novel_text(wrapped) == wrapped


def test_layout_is_stable_on_laid_out_text():
    text = "扉が開いた。\n「来たか」\n\nミレアは座った。\n\n\n三日後。"
    assert style.layout_novel_text(text) == text


def test_event_novel_is_a_third_of_an_episode():
    assert style.EVENT_NOVEL_TARGET_LETTERS == (1700, 2700)
    text = style.style_instruction("event_novel")
    assert "出来事一件は1700〜2700字" in text
    assert "一話は5000〜8000字" not in text
    assert "種(key)" not in text


def test_event_novel_shares_the_episode_novel_style():
    assert style.NOVEL_STYLE_BASE in style.EPISODE_STYLE_BASE
    assert style.NOVEL_STYLE_BASE in style.style_instruction("event_novel")


def test_episode_style_has_no_length_target_but_expands_the_key_with_surrounding_data():
    base = style.EPISODE_STYLE_BASE
    assert "一話は5000〜8000字。" not in base
    assert "字数は、実際に起きることで作る。" in base
    assert "種(key)に場面が足りないときは、足りないぶんを場面として立ててから書く。" in base
    assert base.endswith(
        "種(key)にある出来事は、渡された作品・登場人物・場所・直前の話・関係する設定などの"
        "周辺データを踏まえ、具体的な描写・会話・人物の動きまで詳しく書き起こす。")


@pytest.mark.parametrize("target", ["episode", "event_novel"])
def test_novel_style_leaves_the_scene_count_and_length_to_the_content(target):
    text = style.style_instruction(target)
    assert "場面の数と一場面の長さは決めず、中身に合わせる。" in text
    assert "個の場面に分け" not in text
    assert "一場面は" not in text


@pytest.mark.parametrize("target", ["episode", "event_novel"])
def test_novel_style_sets_how_detailed_to_write(target):
    text = style.style_instruction(target)
    assert "描写の細かさは中身の重さで変える。" in text
    assert "一〜二文で飛ばす" in text


@pytest.mark.parametrize("target", ["episode", "event_novel"])
def test_novel_style_closes_by_whether_the_content_is_over(target):
    text = style.style_instruction(target)
    assert "中身が終わっていないときは、謎・伏線・この先への期待を残して切る。" in text
    assert "中身が終わったときは、余韻を残すか、気の利いた落ちを付けて締める。" in text
    assert "気の利いた落ちを付けない" not in text


def test_episode_prompt_embeds_the_episode_style():
    from ai.claude_code import story_writer

    assert style.style_instruction("episode") in story_writer._SYSTEM_PROMPT
