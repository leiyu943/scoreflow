// Node and browser share this file so seeking, scheduling and exports agree.
(function (root) {
  'use strict';
  function rational(value) {
    if (typeof value === 'number') return value;
    const p = String(value).split('/').map(Number);
    return p.length === 2 && p[1] ? p[0] / p[1] : p[0];
  }
  function normalizeEvents(events) {
    return events.map((e, i) => ({ ...e, id: i, start: rational(e.start), duration: rational(e.duration), velocity: e.velocity ?? 80 }))
      .filter(e => Number.isInteger(e.pitch) && e.pitch >= 0 && e.pitch <= 127 && Number.isFinite(e.start) && e.start >= 0 && Number.isFinite(e.duration) && e.duration > 0)
      .sort((a, b) => a.start - b.start || a.pitch - b.pitch);
  }
  function duration(events) { return events.reduce((m, e) => Math.max(m, e.start + e.duration), 0); }
  function clippedEvents(events, beat) {
    return events.filter(e => e.start + e.duration > beat + 1e-7)
      .map(e => ({ ...e, start: Math.max(0, e.start - beat), duration: e.duration - Math.max(0, beat - e.start) }));
  }
  function anchorsFor(events, geometry, imageWidth) {
    return events.flatMap((event, index) => {
      // HOMR carries an explicit image position for each event; do not shift
      // all later anchors when an individual event lacks geometry.
      const xy = event.image_xy;
      const g = xy ? { x: xy[0] * 1920 / imageWidth, y: xy[1] * 1920 / imageWidth, staff: geometry.length === events.length ? geometry[index]?.staff : undefined, approximate: false }
        : geometry.length === events.length ? geometry[index] : null;
      return g && Number.isFinite(g.x) && Number.isFinite(g.y) ? [{ ...g, beat: event.start, duration: event.duration, pitch: event.pitch, id: event.id }] : [];
    });
  }
  function nearestAnchor(anchors, x, y) {
    if (!anchors.length) return null;
    // Prefer the score row vertically before resolving horizontal position.
    const rows = new Map();
    let groupKey = 0, previousY = -Infinity;
    for (const a of [...anchors].sort((a,b) => a.y - b.y)) {
      if (a.y - previousY > 75) groupKey++;
      previousY = a.y;
      const key = a.staff ?? `row-${groupKey}`;
      const r = rows.get(key) || []; r.push(a); rows.set(key, r);
    }
    const row = [...rows.values()].reduce((best, group) => {
      const center = group.reduce((sum, a) => sum + a.y, 0) / group.length;
      return !best || Math.abs(center - y) < best.distance ? { group, distance: Math.abs(center - y) } : best;
    }, null);
    return row.group.reduce((best, a) => Math.abs(a.x - x) < Math.abs(best.x - x) ? a : best);
  }
  function pageAt(pages,beat) {
    if(!pages.length)return -1;
    let index=0;
    for(let i=1;i<pages.length;i++){if(rational(pages[i].start||0)<=beat+1e-7)index=i;else break;}
    return index;
  }
  const api = { rational, normalizeEvents, duration, clippedEvents, anchorsFor, nearestAnchor, pageAt };
  if (typeof module !== 'undefined') module.exports = api; else root.ScoreMusic = api;
})(globalThis);
