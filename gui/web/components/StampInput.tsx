"use client";

import { useState } from "react";
import Modal from "./Modal";
import { useCalendar } from "@/lib/scope";
import { T } from "@/lib/text";
import {
  clampDay,
  daysInMonth,
  daysInWeek,
  formatStamp,
  hoursInDay,
  minutesInHour,
  monthName,
  monthsInYear,
  parseStamp,
  pad2,
  secondsInMinute,
  weekday,
  weekdayOf,
  type Calendar,
  type StampParts,
} from "@/lib/stamp";

type Props = {
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  /** 数える暦。省けば画面の暦(`CalendarProvider`)。null なら西暦 */
  calendar?: Calendar | null;
};

function defaultParts(calendar: Calendar | null): StampParts {
  // 暦の作品では、今日の日付(西暦)は暦の桁として読めないことがあるので、暦の始まりから選ばせる
  if (calendar) return { ...calendar.offset };
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), hour: 0, minute: 0, second: 0 };
}

/** stamp 欄(年月日時分秒の文字列)向けの、カレンダー形式のポップアップ選択。暦のある作品では、暦の始まりから先を暦の月・日・時間で数える */
export default function StampInput({ value, onChange, disabled, calendar: given }: Props) {
  const context = useCalendar();
  const calendar = given === undefined ? context : given;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<StampParts>(() => parseStamp(value) ?? defaultParts(calendar));

  const openPicker = () => {
    setDraft(parseStamp(value) ?? defaultParts(calendar));
    setOpen(true);
  };

  // 年・月・日を変えたら、その月の日数・その日の時間に収める(暦の始まりの前後で数え方が変わる)
  const update = (change: (d: StampParts) => Partial<StampParts>) =>
    setDraft((d) => clampDay({ ...d, ...change(d) }, calendar));

  const max = daysInMonth(draft.year, draft.month, calendar);
  const week = daysInWeek(draft.year, draft.month, calendar);
  const days = Array.from({ length: max }, (_, i) => i + 1);
  // 週に数える日は月の頭から続くので、1 日の列から詰めて並べる。週に数えない日(月の終わり)は格子の外に並べる
  const inWeek = days.filter((day) => weekdayOf(draft.year, draft.month, day, calendar) !== null);
  const outside = days.filter((day) => weekdayOf(draft.year, draft.month, day, calendar) === null);
  const lead = weekdayOf(draft.year, draft.month, 1, calendar) ?? 0;
  const cells: (number | null)[] = [...Array(lead).fill(null), ...inWeek];
  const months = monthsInYear(draft.year, calendar);
  const hours = hoursInDay(draft.year, draft.month, draft.day, calendar);
  const minutes = minutesInHour(draft.year, draft.month, draft.day, calendar);
  const seconds = secondsInMinute(draft.year, draft.month, draft.day, calendar);
  const dayOfWeek = weekday(draft, calendar);
  const dayButton = (day: number) => (
    <button
      key={day}
      type="button"
      className={`stamp-day ${day === draft.day ? "on" : ""}`}
      onClick={() => update(() => ({ day }))}
    >
      {day}
    </button>
  );
  const named = Array.from({ length: months }, (_, i) => monthName(draft.year, i + 1, calendar));

  const apply = () => {
    onChange(formatStamp(draft));
    setOpen(false);
  };

  return (
    <div style={{ display: "flex", gap: "0.3rem" }}>
      <input
        type="text"
        placeholder="1579/03/02 10:00:00"
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
            {calendar && <div className="stamp-calendar">{T.stamp.calendar(calendar.name)}</div>}
            <div className="stamp-year-row">
              <button type="button" className="ghost" onClick={() => update((d) => ({ year: d.year - 1 }))}>
                ‹
              </button>
              <input
                type="number"
                className="stamp-year"
                value={draft.year}
                onChange={(e) => {
                  const year = Number(e.target.value);
                  update(() => ({ year }));
                }}
              />
              <button type="button" className="ghost" onClick={() => update((d) => ({ year: d.year + 1 }))}>
                ›
              </button>
            </div>
            <div className={`stamp-monthgrid ${named.some(Boolean) ? "named" : ""}`}>
              {named.map((name, i) => (
                <button
                  key={i}
                  type="button"
                  className={`stamp-month ${i + 1 === draft.month ? "on" : ""}`}
                  title={name ?? undefined}
                  onClick={() => update(() => ({ month: i + 1 }))}
                >
                  {name ?? T.stamp.month(i + 1)}
                </button>
              ))}
            </div>
            <div className="stamp-grid" style={{ gridTemplateColumns: `repeat(${week}, 1fr)` }}>
              {cells.map((day, i) => (day == null ? <span key={`lead-${i}`} /> : dayButton(day)))}
            </div>
            {outside.length > 0 && (
              <div className="stamp-outside">
                <span className="stamp-outside-label">{T.stamp.outsideWeek}</span>
                {outside.map(dayButton)}
              </div>
            )}
            <div className="stamp-time">
              <label>
                {T.stamp.hour}
                <select value={draft.hour} onChange={(e) => update(() => ({ hour: Number(e.target.value) }))}>
                  {Array.from({ length: hours }, (_, i) => i).map((h) => (
                    <option key={h} value={h}>
                      {pad2(h)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {T.stamp.minute}
                <select value={draft.minute} onChange={(e) => update(() => ({ minute: Number(e.target.value) }))}>
                  {Array.from({ length: minutes }, (_, i) => i).map((m) => (
                    <option key={m} value={m}>
                      {pad2(m)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {T.stamp.second}
                <select value={draft.second} onChange={(e) => update(() => ({ second: Number(e.target.value) }))}>
                  {Array.from({ length: seconds }, (_, i) => i).map((s) => (
                    <option key={s} value={s}>
                      {pad2(s)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="stamp-preview">
              {formatStamp(draft)}
              {calendar && dayOfWeek !== null && <span className="stamp-weekday">{T.stamp.weekday(dayOfWeek)}</span>}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
