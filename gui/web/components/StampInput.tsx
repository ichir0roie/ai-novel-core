"use client";

import { useState } from "react";
import Modal from "./Modal";
import { T } from "@/lib/text";
import { clampDay, daysInMonth, formatStamp, parseStamp, pad2, weekdayOf, type StampParts } from "@/lib/stamp";

type Props = {
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
};

function defaultParts(): StampParts {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), hour: 0, minute: 0, second: 0 };
}

/** stamp 欄(年月日時分秒の文字列)向けの、カレンダー形式のポップアップ選択。 */
export default function StampInput({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<StampParts>(() => parseStamp(value) ?? defaultParts());

  const openPicker = () => {
    setDraft(parseStamp(value) ?? defaultParts());
    setOpen(true);
  };

  const max = daysInMonth(draft.year, draft.month);
  const lead = weekdayOf(draft.year, draft.month, 1);
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: max }, (_, i) => i + 1)];

  const apply = () => {
    onChange(formatStamp(draft));
    setOpen(false);
  };

  return (
    <div style={{ display: "flex", gap: "0.3rem" }}>
      <input
        type="text"
        placeholder="11579/03/02 10:00:00"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        disabled={disabled}
      />
      <button type="button" className="ghost" onClick={openPicker} disabled={disabled} title={T.stamp.pick}>
        {T.stamp.pickIcon}
      </button>
      {open && (
        <Modal
          title={T.stamp.pick}
          onClose={() => setOpen(false)}
          compact
          actions={
            <>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                {T.stamp.clear}
              </button>
              <span className="spacer" />
              <button type="button" onClick={() => setOpen(false)}>
                {T.create.cancel}
              </button>
              <button type="button" className="primary" onClick={apply}>
                {T.stamp.set}
              </button>
            </>
          }
        >
          <div className="stamp-picker">
            <div className="stamp-year-row">
              <button type="button" className="ghost" onClick={() => setDraft((d) => clampDay({ ...d, year: d.year - 1 }))}>
                ‹
              </button>
              <input
                type="number"
                className="stamp-year"
                value={draft.year}
                onChange={(e) => setDraft((d) => clampDay({ ...d, year: Number(e.target.value) }))}
              />
              <button type="button" className="ghost" onClick={() => setDraft((d) => clampDay({ ...d, year: d.year + 1 }))}>
                ›
              </button>
            </div>
            <div className="stamp-monthgrid">
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`stamp-month ${m === draft.month ? "on" : ""}`}
                  onClick={() => setDraft((d) => clampDay({ ...d, month: m }))}
                >
                  {T.stamp.month(m)}
                </button>
              ))}
            </div>
            <div className="stamp-grid">
              {cells.map((day, i) =>
                day == null ? (
                  <span key={i} />
                ) : (
                  <button
                    key={i}
                    type="button"
                    className={`stamp-day ${day === draft.day ? "on" : ""}`}
                    onClick={() => setDraft((d) => ({ ...d, day }))}
                  >
                    {day}
                  </button>
                ),
              )}
            </div>
            <div className="stamp-time">
              <label>
                {T.stamp.hour}
                <select value={draft.hour} onChange={(e) => setDraft((d) => ({ ...d, hour: Number(e.target.value) }))}>
                  {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                    <option key={h} value={h}>
                      {pad2(h)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {T.stamp.minute}
                <select value={draft.minute} onChange={(e) => setDraft((d) => ({ ...d, minute: Number(e.target.value) }))}>
                  {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                    <option key={m} value={m}>
                      {pad2(m)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {T.stamp.second}
                <select value={draft.second} onChange={(e) => setDraft((d) => ({ ...d, second: Number(e.target.value) }))}>
                  {Array.from({ length: 60 }, (_, i) => i).map((s) => (
                    <option key={s} value={s}>
                      {pad2(s)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="stamp-preview">{formatStamp(draft)}</div>
          </div>
        </Modal>
      )}
    </div>
  );
}
