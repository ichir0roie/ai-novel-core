"use client";

import { useState, type ReactNode } from "react";
import FullscreenText from "./FullscreenText";
import { T } from "@/lib/text";

type Props = {
  /** 画面全体に広げたときの左上の見出し */
  title: string;
  value: string;
  onChange: (value: string) => void;
  /** 広げた画面の ✓ で閉じて保存する。渡さなければ ✓ は閉じるだけ */
  onSave?: () => void;
  /** 広い画面でその場に出す欄 */
  children: ReactNode;
};

/** 大きなテキスト欄。広い画面では children をその場に出し、狭い画面(globals.css の max-width: 960px)では
 * 数行の抜粋のボタンにして、押すと画面全体に広げて直す(FullscreenText)。
 * どちらを出すかは幅で CSS が決める(JS で幅を読むと、読み違えたときに広い画面の欄のまま出る) */
export default function OpenableText({ title, value, onChange, onSave, children }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className="section-inline">{children}</div>
      <button type="button" className="section-open" onClick={() => setOpen(true)}>
        <span className={`section-open-text ${value === "" ? "empty" : ""}`}>{value === "" ? T.record.emptyText : value}</span>
        <span className="section-open-foot">
          <span>{T.record.letters(value.length)}</span>
          <span>{T.record.openFull}</span>
        </span>
      </button>
      {open && (
        <FullscreenText
          title={title}
          value={value}
          onChange={onChange}
          onBack={() => setOpen(false)}
          onSave={
            onSave &&
            (() => {
              setOpen(false);
              onSave();
            })
          }
        />
      )}
    </>
  );
}
