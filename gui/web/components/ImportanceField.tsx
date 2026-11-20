import { T } from "@/lib/text";

// 出来事の重視度の既定。行に値が無いとき(古い API など)はこれとみなす
export const DEFAULT_IMPORTANCE = 5;
const CHOICES = Array.from({ length: 10 }, (_, i) => i + 1);

/** 出来事の重視度(1〜10)を選ぶ欄。出来事の年表・見取り図のモーダルで使う */
export default function ImportanceField({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="field">
      <label>{T.eventTimeline.importance}</label>
      <select value={value} onChange={(e) => onChange(Number(e.target.value))} disabled={disabled}>
        {CHOICES.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      <div className="hint">{T.eventTimeline.importanceHint}</div>
    </div>
  );
}
