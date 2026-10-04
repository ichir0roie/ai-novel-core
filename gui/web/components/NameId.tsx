import { T } from "@/lib/text";

/** 行の名前と id を組にして出す(`T.nameId` と同じ並び)。id は薄く添える。 */
export default function NameId({ name, id }: { name: unknown; id: unknown }) {
  const shown = name == null || name === "" ? null : String(name);
  return (
    <>
      {shown && `${shown} `}
      <span className="name-id">{T.idMark(id)}</span>
    </>
  );
}
