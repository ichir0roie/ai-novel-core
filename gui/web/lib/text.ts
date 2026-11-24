// 画面に出す文言はすべてここに置き、ページ・コンポーネントは文言を直書きしない。
// db の値(場所の category など)は文言ではなく値なので、ここには置かない。

const join = (keys: string[]) => keys.join(", ");
const dash = (v: unknown) => (v == null ? "-" : String(v));
const span = (start: unknown, end: unknown) => (start == null && end == null ? "" : `${start ?? ""} – ${end ?? ""}`);
const idMark = (id: unknown) => `#${id}`;
// 行の名前は、どの画面でも id と組にして出す(名前が無ければ id だけ)。JSX では components/NameId が同じ並びで出す
const nameId = (name: unknown, id: unknown) => (name == null || name === "" ? idMark(id) : `${name} ${idMark(id)}`);

export const T = {
  appName: "novel db",
  appDescription: "Data editing GUI for ai-novel-core",
  pageTitle: (kind: string, record?: string | null) => (record ? `${kind} - ${record}` : kind),

  loading: "Loading…",
  savingOverlay: "Saving…",
  openRecord: "Open record",
  close: "Close",
  required: "required",
  none: "(none)",
  select: "Select",
  filter: "Filter",
  noCandidates: "No candidates",
  yes: "Yes",
  no: "No",
  zoom: "Zoom",
  invalidJson: (error: string) => `Invalid JSON: ${error}`,
  cannotReachApi: (error: string) => `Cannot reach API: ${error} (check that uvicorn is running)`,
  signInRequired: "Sign in required.",
  span,
  idMark,
  nameId,

  nav: {
    menu: "Menu",
    endpoints: "Endpoints",
    timeline: "Timeline",
    eventTimeline: "Event timeline",
    overview: "Overview",
    maps: "Map",
    relations: "Relations",
    expansions: "Expansions",
    search: "Jump to a page (type a table or page name)",
    noMatch: "No matching page",
    searchHint: "Ctrl+K: search pages",
    story: "Story",
    storyTitle: "Story you are working on",
    storyHint: "Times are shown in this story's calendar, and new characters, ideas and places go into it. The page reloads when you change it.",
  },

  home: {
    title: "Tables",
  },

  list: {
    episodesOf: (story: string) => `Episodes of ${story}`,
    stories: "Stories",
    tree: "Tree",
    list: "List",
    add: "+ Add",
    empty: "(empty)",
    searchPlaceholder: "Search name / text",
    search: "Search",
    removeFilter: "Remove this filter",
    filterBy: (label: string) => `Filter by this ${label}`,
    name: "Name",
    text: "Text",
    prev: "Prev",
    next: "Next",
    range: (from: number, to: number, total: number) => `${from}–${to} of ${total}`,
    selectAll: "Select all on this page",
    select: "Select",
    deleteSelected: (count: number) => `Delete selected (${count})`,
    confirmDeleteSelected: (count: number) => `Delete ${count} selected rows? This cannot be undone.`,
    aiBadge: "AI",
    aiBadgeHint: "Added by AI without your review. Editing it makes it yours.",
    origin: "Origin",
    originAll: "All",
    originUser: "Mine",
    originAi: "AI",
    // 暦のある作品の話の一覧で、時刻の列に暦の名を添え、同じ時刻を西暦で並べる
    inCalendar: (column: string, calendar: string) => `${column} (${calendar})`,
    western: (column: string) => `${column} (Western)`,
  },

  expansions: {
    title: "Expansions",
    intro: "Each expansion is one run of the author mode (expand) or one move of a character (auto-act). AI rows can be reverted per expansion.",
    loadFailed: (message: string) => `Could not load expansions: ${message}`,
    empty: "No expansions yet",
    mode: { author: "Author", character: "Character" } as Record<string, string>,
    status: { running: "Running", done: "Done", failed: "Failed", reverted: "Reverted" } as Record<string, string>,
    counts: (added: number, updated: number, deleted: number) => `+${added} ~${updated} −${deleted}`,
    openConflicts: (count: number) => `${count} to decide`,
    prompt: "Prompt",
    summary: "Summary",
    changes: "Changes",
    conflicts: "Decisions",
    noChanges: "No changes recorded",
    noConflicts: "Nothing to decide",
    op: { add: "Added", update: "Changed", delete: "Deleted" } as Record<string, string>,
    before: "Before",
    proposal: "Proposal",
    accept: "Accept",
    acceptHint: "Mark as accepted. Edit the row yourself (or ask expand to apply the proposal).",
    dismiss: "Dismiss",
    revert: "Revert this expansion",
    confirmRevert: (id: number) => `Revert expansion ${id}? Rows it added are deleted and rows it changed go back.`,
    reverted: (count: number) => `Reverted ${count} changes`,
    actionFailed: (message: string) => `Failed: ${message}`,
    actor: "Actor",
    time: "Time",
    filterAll: "All",
  },

  record: {
    clickToEdit: "Click to edit",
    saved: (keys: string[]) => `Saved (${join(keys)})`,
    changed: (keys: string[]) => `Changed: ${join(keys)}`,
    noChanges: "No changes",
    revert: "Revert",
    saveAndBack: "Save and back",
    save: "Save",
    emptySection: "(empty — click to edit)",
    emptyText: "(empty)",
    back: "Back",
    saveAndClose: "Save",
    done: "Done",
    letters: (count: number) => `${count} chars`,
    openFull: "Tap to open ›",
    // 狭い画面で本文の欄を画面全体に広げたときの見出し
    sectionTitles: { plot_text: "プロット", main_text: "本文" } as Record<string, string>,
    edit: "Edit",
    expand: "Click to show all",
    collapse: "Click to fold",
    ageAt: "Age",
    ageInYear: (age: number) => `(age ${age})`,
    delete: "Delete",
    confirmDeleteEpisode: (label: string) =>
      `Delete episode "${label}"? Its cast is removed too. Events, ideas and memes taken from its text stay. This cannot be undone.`,
    confirmDeleteIdea: (label: string, childCount: number) =>
      childCount > 0
        ? `"${label}" has ${childCount} child idea${childCount === 1 ? "" : "s"}. They will be detached (moved to root) and then "${label}" will be deleted. Continue?`
        : `Delete idea "${label}"? Its histories are removed too. This cannot be undone.`,
    confirmDeleteSkill: (label: string) =>
      `Delete skill "${label}"? Its histories and who knows them are removed too. This cannot be undone.`,
    confirmDeleteMotivation: (label: string) =>
      `Delete motivation "${label}"? To mark it fulfilled or gone instead, set its end. This cannot be undone.`,
    deleteFailed: (error: string) => `Could not delete: ${error}`,
    previousEpisode: "◀ Prev",
    nextEpisode: "Next ▶",
    noPreviousEpisode: "No earlier episode in this story",
    noNextEpisode: "No later episode in this story",
  },

  instruction: {
    open: (letters: number) => (letters > 0 ? `AI instruction (${letters} chars)` : "AI instruction (empty)"),
    title: "AI instruction",
    note: "Added to the writing style of the episode text only (not plots or other prose). Leave empty to add nothing.",
  },

  styleEditor: {
    pick: "Pick a row on the left to edit",
    reload: "Reload",
    unsaved: "Unsaved changes",
    discard: "Discard unsaved changes?",
  },

  create: {
    title: (label: string) => `New ${label}`,
    cancel: "Cancel",
    add: "Add",
  },

  endpoints: {
    title: "Call endpoint",
    area: {
      world: "Read world",
      story: "Stories / episodes",
      randomizer: "Add / edit / delete",
      idea: "Idea staging",
      meme: "Memes",
      review: "Review",
      fact_check: "Fact check",
    } as Record<string, string>,
    writesDb: "writes db",
    running: "Running…",
    run: "Run",
    jsonHint: 'Write dicts and arrays as JSON (e.g. {"id": 3, "kind": "概念"} / [1, 2])',
    searchPlaceholder: "Search endpoints",
    selectOne: "Select an endpoint on the left",
  },

  related: {
    relationGraph: { title: "Relation graph", sub: "Only relations involving this character" },
    skills: { title: "Skills", sub: "Skills this character has" },
    mapCentered: { title: "Map centered here", sub: "Map centered on this location" },
    detailMapHere: { title: "Detail map", sub: "The detail map of the parent location, with this one selected" },
    detailMap: { sub: "Locations inside this one (map_detail), which the full map leaves out" },
    storyRoute: { title: "Route map", sub: "Locations of the episodes, in story order" },
    episodeRoute: { title: "Route map", sub: "Locations of this story's episodes, with this one selected" },
    storyTimeline: { title: "Timeline", sub: "This story's episodes, centered on its period" },
    episodeList: "Episode list",
    episodeSummary: (episodes: number, letters: number) => `${episodes} episodes / ${letters.toLocaleString()} chars`,
  },

  episodeContext: {
    title: "In this episode's time & place",
  },

  episodeCharacters: {
    button: (n: number) => `Characters (${n})`,
    modalTitle: "Characters in this episode",
    eventModalTitle: "Characters in this event",
    none: "(no characters yet)",
  },

  characterSheet: {
    record: "Record",
    at: (time: string | null) => (time ? `At ${time}` : "Parameters (no time limits)"),
    born: "Born",
    died: "Died",
    age: "Age",
    location: "Location",
    noText: "(no text)",
    noHistory: "(no history)",
    undated: "Date undecided",
  },

  storyTree: {
    episodes: (n: number) => `${n} episodes`,
    stories: (n: number) => `${n} stories`,
    noStories: "No stories yet",
    moveToRoot: "Move here to make it a top-level story (no parent)",
    move: "Move",
    editHint: "Reorder with ▲▼ or change a parent. Nothing is saved until you apply.",
    apply: (n: number) => `Apply (${n})`,
    applyFailed: (error: string) => `Could not apply: ${error}`,
    discard: "Cancel",
    confirmDiscard: (n: number) => `Discard ${n} unsaved changes?`,
    changeParent: "Change parent",
    cancelMove: "Cancel",
    moveModeHint: (name: string) => `Changing the parent of "${name}" — click another story to make it the new parent (Esc to cancel)`,
    moveUp: "Move up among its siblings",
    moveDown: "Move down among its siblings",
    collapseAll: "Collapse all",
    addChild: "Add child story",
    addEpisode: "Add episode",
  },

  characterTree: {
    characters: (n: number) => `${n} characters`,
    openLocation: "Open location",
    noCharacters: "No characters yet",
    noLocation: "No location",
    noLocationAt: "No location at this time",
    noMatch: "No characters at this location and time",
    collapseAll: "Collapse all",
    location: "Location",
    at: "At",
  },

  ideaTree: {
    empty: "No ideas yet",
    addChild: "Add child",
    move: "Move",
    cancelMove: "Cancel move",
    moveModeHint: (name: string) => `Moving "${name}" — click another idea to make it the new parent`,
    moveToRoot: "Move here to make it a root idea (no parent)",
    moveFailed: (error: string) => `Could not move: ${error}`,
    collapse: "Collapse",
    expand: "Expand",
    collapseAll: "Collapse all",
    delete: "Delete",
    deleteFailed: (error: string) => `Could not delete: ${error}`,
    previousEpisode: "◀ Prev",
    nextEpisode: "Next ▶",
    noPreviousEpisode: "No earlier episode in this story",
    noNextEpisode: "No later episode in this story",
  },

  picker: {
    count: (n: number) => `${n} selected`,
    done: "Done",
  },

  treeSelect: {
    collapse: "Collapse",
    expand: "Expand",
  },

  childList: {
    removeRow: "Remove this row",
    addRow: "+ Add row",
    close: "Close",
    inherited: "Carried over from an earlier row (this row leaves it empty)",
  },

  knowers: {
    label: "knowers",
    add: "+ Add character",
    pickTitle: "Add a character who knows this row",
    remove: "Remove this knower",
    location: "location: ",
    since: (start: string) => `(from ${start})`,
  },

  skills: {
    title: (name: string) => `Skills — ${name}`,
    add: "+ Add skill",
    none: "No skills yet",
    unsaved: "new (not saved)",
    openRecord: "Open this skill's page",
    changes: (n: number) => `${n} skill${n === 1 ? "" : "s"} changed`,
    saved: (n: number) => `Saved ${n} skill${n === 1 ? "" : "s"}`,
    failed: (error: string) => `Could not save: ${error}`,
    confirmDiscard: (n: number) => `Discard unsaved changes to ${n} skill${n === 1 ? "" : "s"}?`,
  },

  knowledge: {
    open: "Organize knowledge",
    openDisabled: "Save or revert the changes on this page first",
    title: (name: string) => `Organize knowledge — ${name}`,
    filter: "Filter characters, ideas and places by name or id",
    onlyKnown: "Only what this character knows",
    characters: "Characters",
    ideas: "Ideas",
    places: "Places",
    placeHint: "Rows whose knower is a place are known by whoever lives there (or below it). Check a row to let this character know it without living there, e.g. while passing through or as a secret.",
    livesHere: (place: string) => `known by living in ${place}`,
    home: "(lives here)",
    self: "(self)",
    knownCount: (n: number) => `${n} known`,
    noMatch: "No match",
    pickSource: "Pick a character, an idea or a place on the left to see its rows. Click a row to switch between known and not known",
    noHistories: "No rows",
    skill: (name: string) => `Skill: ${name}`,
    undated: "undated",
    date: (stamp: string) => stamp.split(" ")[0],
    anywhere: "anywhere",
    adding: "will know",
    removing: "will forget",
    retiming: "new time",
    knownSince: "Known since (empty: from the beginning)",
    defaultSince: "Known since, for newly checked rows",
    changes: (n: number) => `${n} change${n === 1 ? "" : "s"}`,
    undo: "Undo this change",
    confirmDiscard: (n: number) => `Discard ${n} unsaved change${n === 1 ? "" : "s"}?`,
    saved: (n: number) => `Saved ${n} change${n === 1 ? "" : "s"}`,
    failed: (error: string) => `Could not save: ${error}`,
  },

  maps: {
    title: "Location map",
    centeredOn: (name: string) => `Map centered on ${name}`,
    fullMap: "Full map",
    fitLocations: "Fit locations",
    wholePlanet: "Whole planet",
    cannotPlace: (id: number) => `Location id=${id} has neither coordinates nor a polygon, so it cannot be placed on the map. `,
    nonePlaceable: "No location has coordinates or a polygon.",
    radius: (km: number) => `radius ≈ ${Math.round(km).toLocaleString()} km, 1° latitude ≈ ${Math.round((km * Math.PI) / 180).toLocaleString()} km`,
    radiusUnknown: "radius unknown (no area)",
    nameKind: (name: unknown, kind: unknown) => `${name} (${kind ?? ""})`,
    parent: (name: unknown) => `parent: ${dash(name)}`,
    polygonVertices: (n: number) => `polygon: ${n} vertices`,
    environment: (e: string) => `environment: ${e}`,
    lonLatAlt: (lon: number, lat: number, alt: unknown) => `lon ${lon} / lat ${lat} / alt ${dash(alt)}`,
    period: (start: unknown, end: unknown) => `period: ${span(start, end)}`,
    hintClick: "Click a point to show distance and bearing to the other locations. Double-click to open its record.",
    hintCounts: (points: number, shapes: number) => `${points} locations with coordinates, ${shapes} with a polygon. Polygons are drawn as faint areas.`,
    coordinates: "Coordinates",
    environmentDt: "Environment",
    columns: { location: "Location", bearing: "Bearing", distance: "Distance", elevationDiff: "Elevation diff", order: "#", episode: "Episode" },
    sameCoordinates: "same coordinates",
    aboutDegrees: (deg: number) => `≈ ${deg.toFixed(1)}°`,
    aboutKm: (km: number) => `≈ ${km.toLocaleString()} km`,
    altDiffUnknown: "elevation diff unknown",
    sameAltitude: "same altitude",
    altDiff: (up: boolean, m: number) => `${up ? "up" : "down"} ${m.toLocaleString()} m`,
    routeOf: (story: string) => `Route of ${story}`,
    routeCounts: (placed: number, total: number) => `${placed} of ${total} episodes placed on the map. Numbers follow the story order; consecutive episodes in one place share a number.`,
    routeOtherPlanet: (planet: string) => `on ${planet}`,
    routeUnplaced: "no location on the map",
    routeNoLocation: "no location",
    routePlacedAt: (name: string) => `placed at ${name}`,
    routeNone: "No episode of this story has a location on the map.",
  },

  detailMap: {
    title: "Detail map",
    of: (name: string) => `Detail map of ${name}`,
    up: (name: string) => `Up to ${name}`,
    detailMap: (n: number) => `Detail map (${n})`,
    detailMapSub: "Locations inside this one (map_detail), drawn on a map of their own",
    noLocation: "Open this page from a location (?location=<id>).",
    nonePlaced: "No detail location here has coordinates or a polygon. They are listed on the right.",
    noneAtAll: "This location has no detail locations (map_detail) under it.",
    counts: (points: number, shapes: number, unplaced: number) =>
      `${points} with coordinates, ${shapes} with a polygon, ${unplaced} without either.`,
    hintClick: "Click a point to show its details and the distance to the others. Double-click to open its record.",
    places: "Detail locations",
    noCoordinates: "no coordinates",
    scaleUnknown: "radius unknown (no area): scale in degrees",
    scaleM: (m: number) => `${m.toLocaleString()} m`,
    scaleKm: (km: number) => `${km.toLocaleString()} km`,
    scaleDeg: (deg: number) => `${deg}°`,
    aboutM: (m: number) => `≈ ${m.toLocaleString()} m`,
    aboutDegrees: (deg: number) => `≈ ${deg.toFixed(4)}°`,
    sample: "Sample",
  },

  timeline: {
    title: "Timeline",
    centeredOn: (at: string) => `Timeline around ${at}`,
    center: "Center",
    scale: "Scale",
    zoom: ({ unit, count }: { unit: string; count: number }) =>
      `${count} ${unit}${count === 1 ? "" : "s"}`,
    zoomIn: "Show a shorter period down the screen (zoom in)",
    zoomOut: "Show a longer period down the screen (zoom out)",
    squeeze: "Squeeze empty stretches",
    earlier: "▲ Earlier",
    later: "Later ▼",
    story: "Story",
    edit: "Edit",
    editHint: "Drag cards up or down to change their time, or sideways to another story column. Nothing is saved until you apply.",
    apply: (n: number) => `Apply (${n})`,
    applied: (n: number) => `Saved ${n} episode${n === 1 ? "" : "s"}`,
    applyFailed: (error: string) => `Could not apply: ${error}`,
    discard: "Cancel",
    confirmDiscard: (n: number) => `Discard ${n} unsaved changes?`,
    was: (start: string, story: string) => `before: ${start} / ${story}`,
    gap: "No episodes (squeezed)",
    // 暦の作品では、一年・一月を暦の日数(yearDays・monthDays)で数える
    skipped: (days: number, yearDays = 365.2, monthDays = 30.4) =>
      days >= Math.floor(yearDays)
        ? `${Math.round(days / yearDays)}y`
        : days >= 2 * monthDays
          ? `${Math.round(days / monthDays)}mo`
          : `${Math.round(days)}d`,
    openForm: "Open the full form",
    newEpisode: "New episode",
    newEpisodeIn: (story: string) => `Story: ${story}`,
    start: "Start",
    end: "End (empty for a point in time)",
    newEpisodeTitle: "title",
    newEpisodePlot: "plot_text",
    newEpisodeNoStory: "Pick a story row to add here, or open the full form",
    addEpisode: "Add",
    saved: (label: string) => `Saved ${label}`,
    confirmDiscardEdit: "Discard the unsaved time / plot_text?",
  },

  eventTimeline: {
    title: "Event timeline",
    layer: (n: number) => `Layer ${n}`,
    location: "Location",
    outsideFilter: "outside the location filter (shown as a parent)",
    editHint:
      "Drag a card up or down to move it in time (its child events move with it), or drop it on another card to make it that card's child. Nothing is saved until you apply.",
    applied: (n: number) => `Saved ${n} event${n === 1 ? "" : "s"}`,
    gap: "No events (squeezed)",
    parent: (label: string) => `parent: ${label}`,
    becomesChildOf: (label: string) => `→ child of ${label}`,
    becomesRoot: "→ root",
    hidden: "hidden",
    was: (span: string, parent: string) => `before: ${span} / ${parent}`,
    root: "(root)",
    newEvent: "New event",
    newChildOf: (label: string) => `Child of: ${label}`,
    newRoot: "A root event (no parent)",
    newLocation: (label: string) => `Location: ${label}`,
    newParticipants: (labels: string) => `Participants: ${labels}`,
    name: "name",
    start: "Start",
    end: "End (empty for a point in time)",
    text: "text",
    importance: "importance",
    importanceHint: "1–10 (default 5). More important events are placed further left.",
    importanceLine: (n: number) => `importance: ${n}`,
    add: "Add",
    addChild: "Add child event",
    detach: "Detach from parent",
    delete: "Delete",
    confirmDelete: (label: string, children: number) =>
      children > 0
        ? `Delete ${label} and its ${children} child event${children === 1 ? "" : "s"}?`
        : `Delete ${label}?`,
    deleted: (label: string) => `Deleted ${label}`,
    saved: (label: string) => `Saved ${label}`,
    confirmDiscardEdit: "Discard the unsaved name / text / importance?",
  },

  overview: {
    title: "Overview",
    of: (story: string) => `Overview of ${story}`,
    story: "Chapter",
    pickStory: "Pick a chapter to see the events around it.",
    period: (since: string, until: string) => `${since} – ${until}`,
    origin: "Origin",
    originAll: "All",
    originAi: "Character mode (AI)",
    originUser: "Author",
    minSize: "Min size",
    episodes: "Episodes",
    events: "Events",
    gap: "No episodes or events (squeezed)",
    size: (total: number) => `size ${total}`,
    participants: "Participants",
    arc: "Ongoing aim (parent event)",
    legend: "card height = duration · grey episode = another story · line = parent → child (children to the right) · the shown period follows the scroll · drag a card to move it, its top or bottom edge to change the period, or an event onto another event to make it a child · drag from an event's right dot onto another event to make that one its child, or from its left dot to make that one its parent · click a line to remove the link · changes are kept until you press Save at the bottom",
    childOf: (parent: string) => `child of ${parent}`,
    parentOf: (child: string) => `parent of ${child}`,
    linkOf: (parent: string, child: string) => `${parent} → ${child}`,
    unlink: "Remove link",
    pending: (n: number) => `${n} unsaved change${n === 1 ? "" : "s"}`,
    save: (n: number) => `Save (${n})`,
    discard: "Discard",
    applied: (n: number) => `Saved ${n} change${n === 1 ? "" : "s"}`,
    counts: (events: number) => `${events} event${events === 1 ? "" : "s"}`,
    hidden: "hidden",
    confirmDiscardEpisode: "Discard the unsaved time / title / plot_text?",
    added: (label: string) => `Added ${label}`,
    addedEvent: "Added the event",
    addedEventOutside: (since: string, until: string) =>
      `Added the event. It is outside this period (${since} – ${until}), so it is not shown here.`,
    eventsInPeriod: (n: number) => `${n} event${n === 1 ? "" : "s"} in this episode's period`,
    noEventsInPeriod: "(no events in this period with the current filters)",
  },

  episodeSheet: {
    relation: (partner: string, relation: string) => `→ ${partner}: ${relation}`,
    noRelations: "(no relations)",
    toggleRelations: (open: boolean) => (open ? "Hide relations ▴" : "Show relations ▾"),
  },

  stamp: {
    pick: "Pick date & time",
    pickIcon: "📅",
    clear: "Clear",
    set: "Set",
    hour: "H",
    minute: "M",
    second: "S",
    month: (m: number) => `${m}`,
    outsideWeek: "Outside the week",
    weekday: (n: number) => `day ${n} of the week`,
    calendar: (name: string) => `Calendar: ${name} (Western before its start)`,
  },

  relations: {
    title: "Character relations",
    of: (name: string) => `Relations of ${name}`,
    fullGraph: "Full graph",
    noKind: "(no kind)",
    year: "Year",
    allTime: "All time",
    relayout: "Re-layout",
    noCharacters: "No characters.",
    noCharacter: (id: number) => `No character with id=${id}.`,
    hintClick: "Click a character to show their relations, or an arrow to show the relation text. Double-click to open the record. Drag characters to move them.",
    hintCounts: (chars: number, rels: number, year: number | null) =>
      `${chars} characters, ${rels} relations${year == null ? "" : ` (active in year ${year})`}. Arrows point from character_1_id to character_2_id.`,
    columns: { subject: "Subject", relation: "Relation", target: "Target", period: "Period" },
    sex: "Sex",
    period: "Period",
    relation: "Relation",
    noRelations: "No relations.",
    noText: "No text.",
    nameKind: (name: unknown, kind: unknown) => `${name} (${kind ?? ""})`,
    sexOf: (sex: string) => `sex: ${sex}`,
    periodOf: (span: string) => `period: ${span}`,
    arrow: (from: string, to: string, relation: string | null) => `${from} → ${to}: ${relation ?? ""}`,
  },

  // 見出しの右の「?」で開く、画面ごとの解説(components/PageHelp)。ボタン・欄の名前は画面の表示のまま書く
  help: {
    button: "この画面の説明",
    title: (page: string) => `${page} の説明`,

    common: {
      heading: "どの画面でも",
      points: [
        "左上の Menu か Ctrl+K(⌘K)で、表・画面の名前を打って移れる。",
        "Menu の Story は、いま作業している作品。どの画面の時刻もその作品の暦で出し、新しい人物・アイデア・場所はその作品に入る。変えると画面を読み直す。",
        "保存できる画面では Ctrl+S(⌘S)で保存する。",
        "行・札・リンクを Ctrl+クリック(⌘クリック)すると別のタブで開く。この画面の書きかけは残る。",
        "点線の下線の付いた名前(列名・子の一覧)にかざすと、その意味が出る。文は db/schema.py のコメント。",
        "出自(Origin): Mine(user)は自分が作った・直した行、AI は AI が確かめを経ずに足した行で、AI の札が付く。AI は自分の行を直さない・消さない。AI の行を直すと自分の行になる。",
      ],
    },

    home: {
      intro: "始めの画面。札一枚が db の表一つで、行の数を出す。札を押すとその表の一覧を開く。",
      sections: [
        {
          heading: "表",
          points: [
            "story: 作品と、その章・外伝。話(episode)は作品から開くので、ここに札は無い。",
            "character: 人物。国・組織・集団・物もここに入る。人物どうしの関係(character_relation)は人物から開くので、ここに札は無い。",
            "character_skill / character_motivation: 人物のスキル・装いと、いま何をしたがっているか。",
            "event: ある時刻・場所で起きた出来事。大きな出来事の中に小さな出来事を入れ子にする。",
            "location: 場所。世界・惑星から部屋までの木。",
            "idea: 世界の概念・技術・制度など。木で持つ。",
            "meme: 人物のあいだで移り広がる信条・欲求・価値観。話の本文から抜き出す。",
            "oracle: 創作・AI についての自分の覚え書き。物語のデータではない。",
            "style_preference: AI に書かせる文の書き方。文の種類ごとに一行。",
            "custom_stamp: 作品・行が時刻を数える暦。",
          ],
        },
        {
          heading: "ほかの画面(Menu から)",
          points: [
            "Timeline: どの作品の話も一本の時間軸に並べる。",
            "Event timeline: 出来事を時間軸に並べ、どの出来事がどれを含むかで配置する。",
            "Overview: 章を一つ選び、その時期の話と出来事を並べて見渡す。",
            "Map: 場所を惑星の地図に置く。作品の道のりも出せる。",
            "Relations: 人物の関係のグラフ。",
            "Expansions: 作者モード(ex)と人物モード(auto)で AI が世界に足したものの記録。丸ごと取り消せる。",
            "Endpoints: data_access_logic の入口を手で呼ぶ。",
          ],
        },
      ],
    },

    tableList: {
      intro: "一つの表の行を、一ページ 50 件で並べる。story・idea・character はツリーでも見られる。",
      sections: [
        {
          heading: "行を探す",
          points: [
            "Search は名前と本文から探す。",
            "Origin で、自分の行(Mine)か、AI が確かめを経ずに足した行(AI)だけに絞る。",
            "参照の列(作品・人物・親など)の値を押すと、その値の行だけに絞る。絞り込みは札(チップ)で出て、押すと外れる。",
            "列の見出しを押すとその列で並べ、もう一度押すと逆順にする。",
            "Prev / Next でページを移る。",
          ],
        },
        {
          heading: "開く・足す",
          points: [
            "行を押すと開く。+ Add で新しい行の欄を開く。",
            "Tree / List で表示を切り替える。Tree は親子を、List はただの表を出す。",
            "AI の札の付いた行は、AI が確かめを経ずに足した行。開いて直すと自分の行になる。",
          ],
        },
        {
          heading: "ツリー表示",
          points: [
            "story: 作品と、その章・話。▲▼ で兄弟の中の順を変え、親を付け替えてから Apply で保存する。押すまで何も保存しない。作品の行から子の作品・話を足せる。",
            "idea: アイデアを親の下に並べる。別のアイデアの下(か根)へ移す・子を足す・消すができる。消したアイデアの子は根へ移る。",
            "character: 人物を住む場所ごとにまとめる。場所と時刻(At)を選ぶと、そのときそこにいる人物を出す。",
          ],
        },
      ],
    },

    record: {
      intro: "表の一行。左に欄、右に長い文(プロット・本文・来歴など)を出す。見出しの名前を押すと名前を直せる。",
      sections: [
        {
          heading: "直す・保存する",
          points: [
            "欄を押すと直せる。Save(か Ctrl+S)を押すまで保存しない。下のバーに直した欄が出る。",
            "Revert は保存していない直しを捨てる。Save and back は保存して一覧へ戻る。",
            "Delete は話・アイデア・スキル・モチベーションにだけある。ほかの行は多くの行から指されるので消さずに残す。",
          ],
        },
        {
          heading: "子の行",
          points: [
            "来歴(histories)・居場所(locations)・月(months)などの一覧は、この行に属する行。行ごとに start(と end)を持ち、+ Add row で足す。",
            "start が空の行は、たいていの一覧では「初めから」。人物・関係・スキルの来歴では「時期未定」(まだ時期を決めていない構想)で、最後に並び、話・出来事には渡さない。",
            "後の行が空にした欄は、前の行から引き継いだ値を薄く出す。",
            "knowers は、その行を知る相手。人物か場所で、場所ならそこと配下に住む人物がみな知る。人物が知るのは、knowers に自分(か住む場所)が入っている行だけ。",
          ],
        },
        {
          heading: "そのほかのボタン",
          points: [
            "左のリンクから関わる画面へ移る: 人物の関係のグラフ・スキル、場所を中心にした地図、作品の道のりの地図とタイムライン、話の一覧。",
            "AI instruction(作品・話): その作品・話で AI が書くときに足す指示。空なら何も足さない。",
            "Organize knowledge(人物): その人物がどの人物・アイデア・場所を、いつから知るかを決める。先にこの画面を保存か Revert しておく。",
            "話: ◀ Prev / Next ▶ で作品の中を時刻の順に移る。Characters (n) で登場人物を選ぶ。「In this episode's time & place」に、その話の時刻・場所のまわりを出す。",
          ],
        },
      ],
    },

    create: {
      intro: "新しい行の欄。required の欄は埋める。Add で保存してその行を開き、Cancel で一覧へ戻る。",
      sections: [
        {
          heading: "メモ",
          points: [
            "時刻は、行の属する作品の暦で読む。新しい人物・アイデア・場所は、Menu で選んでいる作品から始まる。",
            "新しい話は、同じ作品の前の話の場所と視点を写す。自分で入れた欄は上書きしない。",
            "「Add child」などから開くと、親などの欄が初めから埋まっている。",
          ],
        },
      ],
    },

    styleEditor: {
      intro: "AI に渡す書き方の指示。左で行を選ぶと、右で直せる。",
      sections: [
        {
          heading: "行の使われ方",
          points: [
            "行は範囲(scope、文の種類)ごとに一つ。「全体」の行は AI が書くすべての文に、ほかの行はその種類の文(話の本文・プロット・人物・出来事など)にだけ足す。",
            "話の本文では、全体 → 作品の指示 → 本文 → 推敲 → 話の指示 の順に足す。",
            "AI が書くたびに db から読むので、直せばすぐ効く。行の無い範囲は何も足さない。",
            "Reload で行を読み直す。保存していない直しは、保存するか捨てるまで残る。",
          ],
        },
      ],
    },

    tables: {
      story: {
        heading: "この表: story",
        points: [
          "作品。章・外伝は子の作品(parent_story_id)にする。話は一つの作品に属し、書くときは親の作品の筋書きまでたどる。",
          "作品の中の話は、id でなく start の順に並ぶ。",
          "custom_stamp_id: この作品で足す行の暦の既定。",
          "instruction: この作品と子の作品で AI が書くすべての文に足す指示。",
          "narou_novel_id: 小説家になろうへ投稿する小説の番号(小説管理の画面の URL にある番号で、N コードではない)。空の章は、番号のある一番近い親の小説へ投稿する。",
          "display_order: 兄弟の作品の中の並び。小さいほど上。",
        ],
      },
      episode: {
        heading: "この表: episode",
        points: [
          "話一つ。時刻(start / end)・視点の人物・場所・登場人物・プロット・本文を持つ。",
          "plot_text は自分で書く話の中身。main_text は本文で、まだ書いていない話(枠だけ)は空。Claude Code の「ep<話id>」などで埋める。",
          "letters は main_text から数えた字数。",
          "instruction は、この話の本文を書くときに書き方へ足す指示(プロットなどほかの文には足さない)。",
          "話を消すと登場人物の結びも消える。本文から抜き出した出来事・アイデア・ミームは残る。",
        ],
      },
      character: {
        heading: "この表: character",
        points: [
          "人物。人物のように動くもの(国・組織・商会・氏族・集団・物)も入る(kind で分ける)。",
          "text: 人物の芯(経歴・立場・性格)。どの話・出来事にも渡し、関係のある人物が知る。",
          "appearance: 見て分かること。meme: 持つミーム。principle: その人物を動かすもの(行動原理)。plot: その人物について進めたい筋書き。",
          "main_character: ランダム生成と人物モード(auto)は、メインキャラクターでない人物だけを動かす。",
          "end: 死んだ・無くなった時刻。生きているあいだは空。",
          "histories: 出来事ごとの来歴で、行ごとに knowers を持つ。parameters: ある時刻からの性格と影響力。locations: どこに、いつから住むか。",
        ],
      },
      character_relation: {
        heading: "この表: character_relation",
        points: [
          "character_1 から見た character_2 との関係(片向き。逆向きは別の行)。",
          "relation: 短い名前(母・師・宿敵など)。text: 関係の芯。",
          "start / end: 関係の続く時期。start が空なら初めから、end が空なら続いている。",
          "histories: 関係の中で起きたことを、出来事ごとの行で持つ。",
        ],
      },
      character_skill: {
        heading: "この表: character_skill",
        points: [
          "人物のスキル(技・術・技能)。kind が「装い」なら、身に着けている物一つ(外套・剣など)。",
          "text: スキルの本質(何ができるか・仕組み・限界)。作者の側(自分と語り部)だけが読み、人物役やほかの AI には渡さない。",
          "histories: 身につけた・伸びた・失ったなどの行。人物が知るのはこの行だけ。装いは、着けた・傷んだ・手放したなどの行で、見た人はだれでも知る。",
        ],
      },
      character_motivation: {
        heading: "この表: character_motivation",
        points: [
          "人物がいま何をしたがっているかと、その理由。一つの思いごとに一行。",
          "strength: 1 気にかかる程度 / 2 機会があればしたい / 3 手間をかけてもしたい / 4 ほかを後回しにしてもしたい / 5 何を捨てても果たしたい。",
          "start から効き、end が空のあいだ効いている。果たした・消えたら、消さずに end を付ける。強さが変わったら、前の行を終えて新しい強さの行を足す。",
          "本人の内心なので、その人物の人物役だけが読む。",
        ],
      },
      event: {
        heading: "この表: event",
        points: [
          "ある時刻(time。期間なら終わりは end)と場所で起きたことと、その当事者。",
          "出来事は入れ子にする。parent_event_id は、この出来事を含む大きな出来事。",
          "hidden: 書くときに読む場所の断面に出さない(full で読むときだけ出す)。",
        ],
      },
      location: {
        heading: "この表: location",
        points: [
          "場所は木(parent_id)にする。場所に効く断面・knowers・アイデアは、その配下の場所にも効く。",
          "位置: 世界線 W・惑星 P・経度 / 緯度 / 高度、または輪郭(GeoJSON の polygon。地図に面で描く)。",
          "area: 単位は決めないが、子は親より狭く、兄弟を足しても親を超えない。",
          "sample_region / sample_culture / sample_era: 地理・暮らし・技術の水準の手がかりにする実在の地域・文化・時代。名前をそのまま使うものではない。",
          "active_random_generation: ランダム生成がこの場所を選んでよいか。",
        ],
      },
      idea: {
        heading: "この表: idea",
        points: [
          "世界の概念・技術・制度など。木(parent_idea_id)で持ち、kind が種別。",
          "text: アイデアの本質。作者の側だけが読む。",
          "histories: 場所・時期ごとの、作中での呼び名と受け止め方。人物が知るのは knowers に入っている行だけで、その行の効く場所・時期の人物は、その名前でアイデアを呼ぶ。",
          "アイデアを消すと、その子は根へ移る。",
        ],
      },
      meme: {
        heading: "この表: meme",
        points: [
          "人物のあいだで移り広がる信条・欲求・境遇・集団・理(category)。",
          "確定した話の本文から抜き出す。どこから抜き出したか・だれが持つかは持たない。",
          "anti_meme_id: 反転したミーム。対の二行が互いを指す。category・anti_meme が空なら、次の抽出で AI が埋める。",
          "行にチェックを入れて Delete selected で、まとめて間引ける。",
        ],
      },
      oracle: {
        heading: "この表: oracle",
        points: ["創作・AI についての自分の覚え書き。題を付けて持つ。物語のデータではなく、話を書くときには渡さない。"],
      },
      style_preference: {
        heading: "この表: style_preference",
        points: ["範囲ごとに一行。List で普通の表として見られる。既定の表示は編集の画面。"],
      },
      custom_stamp: {
        heading: "この表: custom_stamp",
        points: [
          "暦。作品・話・出来事・人物・アイデア・場所・関係がこれを指し、その行(と子の行)の時刻をこの暦で出す。",
          "時刻は db に西暦のまま入れ、出すとき・入れるときだけ暦で数える。暦の始まりより前は西暦で出す。",
          "offset: この暦の 0 年 1 月 1 日 0 時に当たる西暦の時刻。",
          "hours_per_day / minutes_per_hour / seconds_per_minute: 一日の長さ(秒は地球の秒)。days_per_week: 一週の日数。",
          "months: 一年の月とその日数を子の行で持つ。",
        ],
      },
    } as Record<string, HelpSection>,

    endpoints: {
      intro: "data_access_logic の入口を手で呼ぶ。Claude が db を読み書きするのと同じ入口。",
      sections: [
        {
          heading: "使い方",
          points: [
            "左で入口を選ぶ。入口は分野ごとにまとまっている: 世界を読む・作品と話・足す/直す/消す・アイデアの仮置き・ミーム・確かめ・事実の確かめ。",
            "検索欄は id と説明で絞る。",
            "引数を入れて Run を押す。辞書と配列は JSON で書く(例: {\"id\": 3}、[1, 2])。JSON で読めないものは文字列のまま渡す。",
            "「writes db」の付いた入口はデータを変える。本物の db に書くので、引数を確かめてから押す。",
            "結果は下に JSON で出る。",
          ],
        },
      ],
    },

    expansions: {
      intro: "世界の展開の記録。展開一つは、作者モード(Claude Code の ex)の一回か、人物モード(auto)で人物が動いた一手。その間に AI が足した・直した・消した行をすべて記録するので、一回ぶんを丸ごと取り消せる。",
      sections: [
        {
          heading: "一覧",
          points: [
            "Mode: Author(作者の一言を AI が広げた)か Character(サブキャラクターが自分から動いた)。上で Mode を絞れる。",
            "+足した ~直した −消した: その回に触れた行の数。",
            "「n to decide」: まだ判断を待っている食い違いの数。",
            "Status: Running(実行中)・Done(済み)・Failed(失敗)・Reverted(取り消し済み)。",
          ],
        },
        {
          heading: "展開一つ",
          points: [
            "Prompt: 作者の一言(作者モード)か、人物の狙い(人物モード)。作者の一言は本筋の正として、後の展開も読む。",
            "Summary: 何を足し・直したかの要約。Actor と Time: 動いた人物と時刻(人物モード)。",
            "Changes: その回に触れた行と、直す前の値。",
          ],
        },
        {
          heading: "Decisions(作者の判断)",
          points: [
            "AI は作者の行を直さない。展開が作者の行と食い違ったら、直し方の案を付けた食い違いを残す。",
            "Accept は「受け入れた」にする。そのあと行を自分で直すか、ex に案を当てるよう頼む。",
            "Dismiss は何も変えずに閉じる。",
            "未決の食い違いは、後回しの確かめの一覧にも出る。",
          ],
        },
        {
          heading: "Revert(取り消し)",
          points: [
            "Revert this expansion は、その回に足した行を消し、直した・消した行を元の値に戻す。",
            "その後で自分か別の展開がその行を直していたら、何も戻さずに止まり、その行を示す。後の作業は失われない。",
          ],
        },
      ],
    },

    timeline: {
      intro: "話を一本の時間軸に並べる。時間は上から下へ流れる。列一つが作品(章・外伝は親の作品の下)、札一枚が話で、start から end までの高さを取る。",
      sections: [
        {
          heading: "見る範囲を変える",
          points: [
            "Center: 画面の真ん中の時刻。▲ Earlier / Later ▼ で一画面ぶん移る。",
            "Scale − / +: 一画面に見せる期間を短く・長くする。",
            "Squeeze empty stretches: 話の無い期間を細い隙間に詰め、飛ばした長さを添える。",
            "Story: 一つの作品と子の作品だけを出す。時刻はその作品の暦で出す。",
            "列の見出しの開閉の印を押すと、その列を畳む・開く。畳んだ列は話を小さな印で出す。作品の名前を押すと作品を開く。",
          ],
        },
        {
          heading: "直す",
          points: [
            "札にかざすと中身が出る。押すとその場で時刻と plot_text を直せる。ほかの欄は「Open the full form」から。",
            "作品の列の空いた所を押すと、その時刻に新しい話を足す。",
            "Edit: 札を上下に動かすと時刻が、横の作品の列へ動かすと作品が変わる。Apply を押すまで保存しない。Cancel で動かしたものを捨てる。",
          ],
        },
      ],
    },

    eventTimeline: {
      intro: "出来事を時間軸に並べ、どの出来事がどれを含むかで配置する。根の出来事は一番左の層に置き、子の出来事は親の右に置いて線で結ぶ。時期の重なる出来事は、重視度(1〜10、既定 5)の小さい方が右の層へずれ、重視度が同じなら遅い方がずれる。",
      sections: [
        {
          heading: "見る範囲を変える",
          points: [
            "Center・▲ Earlier / Later ▼・Scale・Squeeze empty stretches は Timeline と同じ。",
            "Location: その場所と配下で起きた出来事だけを出す。絞り込みの外にある親は、線が切れないよう薄く出す。",
          ],
        },
        {
          heading: "直す",
          points: [
            "札を押すと、重視度・名前・本文を直す・子の出来事を足す・親から外す・(子ごと)消す・行のページを開く ができる。",
            "空いた所を押すと、その時刻に出来事を足す。出来事の右の所を押したら、その子になる。",
            "Edit: 札を上下に動かすと時刻が変わる(子も一緒に動く)。別の札に落とすと、その子になる。Apply を押すまで保存しない。",
          ],
        },
      ],
    },

    overview: {
      intro: "章を一つ選び、その章の話の時期に重なる話と出来事を一本の時間軸に並べて見渡す。話の時期の外でも、画面に見えている期間の出来事は出す(スクロールや縮尺の変更に合わせて読み足す)。",
      sections: [
        {
          heading: "列",
          points: [
            "Episodes: 話の札。どの作品の話も一つの列に並べ、選んだ章の外の話は灰色で出す。札の高さが期間。",
            "Events: 出来事の札。親から子へ線で結び、子は親の右に置く。重視度(1〜10、既定 5)の大きい出来事ほど左に置く。出来事は章に結ばないので、期間の重なるものをすべて出す。",
            "上の一行の凡例が、この見方の短い版。",
          ],
        },
        {
          heading: "絞り込み",
          points: [
            "Origin: 人物モード(AI)が足した出来事だけ、か作者の出来事だけを出す。",
            "Min size: これより小さい人物モードの出来事を隠す。大きさ = 関わった人数 + 移動 + 新しい場所 + 新しい人物 + アイデア。",
            "Scale と Squeeze empty stretches は Timeline と同じ。",
          ],
        },
        {
          heading: "操作",
          points: [
            "札を掴んで上下に動かすと時刻が変わる。上端・下端を掴むと期間を変える。",
            "札を動かす・親子を結ぶ・外すのは、すぐには保存しない。変えた札は赤い破線で出し、画面の下の真ん中に出る Save でまとめて保存する(Ctrl+S でも)。Discard で捨てる。保存せずに章を変える・画面を離れるときは確かめる。",
            "出来事の札を別の出来事の札に重ねて離すと、その子にする(時刻は動かさない)。親子の線を押して Remove link を押すと、親を外す。",
            "出来事の札の左右の丸点(マウスでは札に乗せると出る)から線を引き、別の出来事の札で離すと親子を結ぶ。右の点からなら離した札を子に、左の点からなら離した札を親にする。親子が輪になる札とは結べない。",
            "話の札を押すと、時刻・タイトル・プロットを直せる。話の列の空いた所を押すと、その時刻に足す話を左の枠に出す。左の枠には、その話の期間に重なる出来事も出る。",
            "出来事の札を押すと詳細(当事者・動いた人物・巻きこまれた人物・狙いとやり取り・作った展開)が出て、重視度・名前・本文を直せる。そこから出来事や Expansions を開ける。Delete で、子孫の出来事(この画面に読んでいない期間の分も)ごと消す。消す前に件数を出して確かめる。",
            "出来事の列の空いた所を押すと、その時刻に出来事を足す。章の時期の外に足した出来事は、読み直すとこの画面には出ない。",
          ],
        },
      ],
    },

    maps: {
      intro: "経緯度か輪郭を持つ場所を、惑星の地図に置く。点が場所、薄い面が輪郭。どちらも持たない場所は置けないので、一覧で出す。",
      sections: [
        {
          heading: "地図",
          points: [
            "惑星がいくつかあれば、上のボタンで切り替える。",
            "Fit locations は置いた場所に合わせて寄せ、Whole planet は惑星全体を出す。",
            "点を押すと、ほかの場所までの距離・方角・高さの差を一覧で出す。ダブルクリックでその行を開く。",
            "場所の行の「Map centered here」から開くと、その場所を真ん中に出す。Full map で全体に戻る。",
            "詳細の場所(map_detail。町の中の場所・周りのエリア・人物の家など)は全体の地図に出さない。詳細の子を持つ場所を押すと、横の欄の「Detail map」から詳細マップへ移る。",
          ],
        },
        {
          heading: "道のりの地図",
          points: [
            "作品か話から開くと、作品の話の場所を作品の順に番号を振って出す。続けて同じ場所の話は同じ番号にまとめる。",
            "別の惑星の話と、地図に置けない場所の話は、地図の下に一覧で出す。",
          ],
        },
      ],
    },

    detailMap: {
      intro: "場所の配下の詳細の場所(map_detail)を、その場所の狭い範囲の地図に置く。全体の地図には出さない場所を、ここで見る。",
      sections: [
        {
          heading: "地図",
          points: [
            "開いた場所から、詳細の場所だけをたどって届く子孫を出す。詳細でない子(全体の地図に出る場所)より下は、その子の詳細マップに出す。",
            "破線の面と灰色の印は、開いた場所そのもの。左下の物差しは、惑星の半径(area)から出す。半径が分からなければ度で出す。",
            "点を押すと横に詳細と、ほかの場所までの距離・方角を出す。ダブルクリックでその行を開く。",
            "詳細の子を持つ場所は「Detail map」で、その場所の詳細マップへ一段降りる。Up to で一段上がり、Full map で全体の地図へ戻る。",
            "経緯度も輪郭も持たない詳細の場所は、横の一覧に親子の木で出す。",
          ],
        },
      ],
    },

    relations: {
      intro: "人物とその関係のグラフ。矢印は character_1 から character_2 へ向き、前者から見た後者との関係を表す。",
      sections: [
        {
          heading: "使い方",
          points: [
            "上のチェックで、種別(人物・国・組織など)ごとに出す・隠す。",
            "Year: その年に続いている関係だけを出す。All time なら全部。",
            "人物を押すとその関係を一覧で出し、矢印を押すと関係の本文を出す。",
            "人物をダブルクリックすると行を開く。人物はドラッグで動かせ、Re-layout で並べ直す。",
            "人物の行の「Relation graph」から開くと、その人物と直接つながる相手だけを出す。Full graph で全員に戻る。",
            "人物が多いと、全員の表示は描くのに時間がかかる。",
          ],
        },
      ],
    },
  },
} as const;

export type HelpSection = { readonly heading: string; readonly points: readonly string[] };
export type Help = { readonly intro: string; readonly sections: readonly HelpSection[] };
