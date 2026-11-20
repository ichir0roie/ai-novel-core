"use client";

import { useState } from "react";
import Modal from "./Modal";
import { T, type Help, type HelpSection } from "@/lib/text";

/** 見出しの右に置く「?」。押すとその画面の解説をモーダルで出す。どの画面にも共通の操作は最後に足す。 */
export default function PageHelp({ page, help, extra = [] }: { page: string; help: Help; extra?: readonly HelpSection[] }) {
  const [open, setOpen] = useState(false);
  const sections = [...extra, ...help.sections, T.help.common];
  return (
    <>
      <button type="button" className="page-help" title={T.help.button} aria-label={T.help.button} onClick={() => setOpen(true)}>
        ?
      </button>
      {open && (
        <Modal title={T.help.title(page)} onClose={() => setOpen(false)}>
          <div className="page-help-body">
            <p>{help.intro}</p>
            {sections.map((section) => (
              <section key={section.heading}>
                <h3>{section.heading}</h3>
                <ul>
                  {section.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}
