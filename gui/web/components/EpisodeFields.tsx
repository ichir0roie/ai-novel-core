"use client";

import { AutoGrowTextarea } from "@/components/FieldInput";
import OpenableText from "@/components/OpenableText";
import StampInput from "@/components/StampInput";
import { createRecord, getPreviousEpisode, type Rec } from "@/lib/api";
import { T } from "@/lib/text";

/** 話の時刻・タイトル・プロットの書きかけ。時刻は空なら null。title を省けばタイトルの欄を出さない */
export type EpisodeDraft = { start: string | null; end: string | null; title?: string; plot: string };

// 追加ページと同じく、同じ作品の前の話から写す欄(lib/previousEpisode.ts)
const COPIED_KEYS = ["location_id", "viewpoint_character_id", "character_ids"] as const;

/** 話を足す。`initial` に `story_id` が要る。同じ作品で開始より前の話から場所・視点・登場人物を写す */
export async function addEpisode(initial: Rec, draft: EpisodeDraft) {
  const data: Rec = { ...initial, start: draft.start, end: draft.end, title: draft.title ?? "", plot_text: draft.plot };
  const previous = await getPreviousEpisode(initial.story_id as number, draft.start);
  for (const key of COPIED_KEYS) {
    const v = previous?.[key];
    if (v != null && !(Array.isArray(v) && v.length === 0)) data[key] = v;
  }
  return createRecord("episode", data);
}

type Props = {
  value: EpisodeDraft;
  onChange: (value: EpisodeDraft) => void;
  disabled?: boolean;
  /** プロットを画面全体に広げたときの ✓ で保存する */
  onSave?: () => void;
};

/** タイムライン・見取り図から話を足す・直すときの欄(開始・終了・タイトル・プロット) */
export default function EpisodeFields({ value, onChange, disabled, onSave }: Props) {
  return (
    <>
      <div className="field">
        <label>{T.timeline.start}</label>
        <StampInput value={value.start} onChange={(start) => onChange({ ...value, start })} disabled={disabled} />
      </div>
      <div className="field">
        <label>{T.timeline.end}</label>
        <StampInput value={value.end} onChange={(end) => onChange({ ...value, end })} disabled={disabled} />
      </div>
      {value.title !== undefined && (
        <div className="field">
          <label>{T.timeline.newEpisodeTitle}</label>
          <input
            type="text"
            value={value.title}
            onChange={(e) => onChange({ ...value, title: e.target.value })}
            disabled={disabled}
          />
        </div>
      )}
      {/* プレビューと切り替える欄(MarkdownField)だと、外れたときに高さが変わって下のボタンの押下が外れるので、常に書ける欄にする */}
      <div className="field">
        <label>{T.timeline.newEpisodePlot}</label>
        <OpenableText
          title={T.timeline.newEpisodePlot}
          value={value.plot}
          onChange={(plot) => onChange({ ...value, plot })}
          onSave={onSave}
        >
          <AutoGrowTextarea value={value.plot} onChange={(plot) => onChange({ ...value, plot })} />
        </OpenableText>
      </div>
    </>
  );
}
