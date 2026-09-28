import type { Option } from "./api";

/** プルダウンの選択肢(`Option`)を `parent_id` で木にする。場所・アイデアのように
 * 自己参照で親子を持つテーブルの選択(`ReferenceTreeSelect`)に使う。*/

export type OptionNode = {
  id: number;
  label: string;
  children: OptionNode[];
};

export function buildOptionTree(options: Option[]): OptionNode[] {
  const known = new Set(options.map((o) => o.id));
  const childrenOf = new Map<number | null, Option[]>();
  for (const option of [...options].sort((a, b) => a.id - b.id)) {
    const parent = option.parent_id ?? null;
    const key = parent !== null && known.has(parent) ? parent : null;
    childrenOf.set(key, [...(childrenOf.get(key) ?? []), option]);
  }
  const node = (option: Option): OptionNode => ({
    id: option.id,
    label: option.label,
    children: (childrenOf.get(option.id) ?? []).map(node),
  });
  return (childrenOf.get(null) ?? []).map(node);
}
