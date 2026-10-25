const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('../app/music.cjs');
const {makeMidi,INSTRUMENTS}=require('../app/midi.cjs');
test('sample instrument selection changes GM program without changing notes or times',()=>{
  const events=[{pitch:64,start:'1/3',duration:'2/3',velocity:80}];
  const guitar=makeMidi(events,[{start:0,meter:[4,4]}],120,24),piano=makeMidi(events,[{start:0,meter:[4,4]}],120,0);
  assert.equal(guitar[31],24);assert.equal(piano[31],0);piano[31]=24;assert.deepEqual(guitar,piano);assert.equal(INSTRUMENTS.length,7);
});
test('sampled MIDI preserves triplet tick positions',()=>{
  const file=makeMidi([{pitch:64,start:'1/3',duration:'2/3'}],[],120,24);
  assert.ok(file.includes(Buffer.from([0x82,0x40,0x90,64,80])));
});
test('page navigation switches at global page starts including silent endings',()=>{
  const pages=[{start:0,duration:4},{start:4,duration:3},{start:7,duration:2}];
  assert.equal(M.pageAt(pages,3.9),0);assert.equal(M.pageAt(pages,4),1);assert.equal(M.pageAt(pages,7.1),2);assert.equal(M.pageAt(pages,9),2);
});
test('MIDI end includes final page trailing silence',()=>{
  const file=makeMidi([{pitch:60,start:0,duration:1}],[],120,24,4);
  assert.deepEqual([...file.subarray(-5)],[0x96,0x40,255,47,0]);
});
test('rational event time supports triplets and preserves chords', () => {
  const events=M.normalizeEvents([{pitch:67,start:'1/3',duration:'2/3'},{pitch:60,start:'1/3',duration:'1/6'}]);
  assert.equal(events.length,2); assert.equal(events[0].pitch,60); assert.equal(events[1].start,1/3); assert.equal(M.duration(events),1);
});
test('seeking clips notes already sounding and omits expired notes', () => {
  const events=[{pitch:60,start:0,duration:3},{pitch:64,start:1,duration:1},{pitch:67,start:4,duration:1}];
  assert.deepEqual(M.clippedEvents(events,2).map(e=>[e.pitch,e.start,e.duration]),[[60,0,1],[67,2,1]]);
});
test('one absent geometry point does not shift subsequent source coordinates', () => {
  const events=M.normalizeEvents([{pitch:60,start:0,duration:1,image_xy:[100,100]},{pitch:64,start:1,duration:1},{pitch:67,start:2,duration:1,image_xy:[500,100]}]);
  const anchors=M.anchorsFor(events,[{x:192,y:192},{x:960,y:192}],1000);
  assert.equal(anchors.length,2); assert.equal(anchors[1].beat,2);assert.equal(anchors[1].x,960);
});
test('clicking the second row resolves that row even when first-row x is closer', () => {
  const anchors=[{x:100,y:100,beat:0},{x:500,y:135,beat:1},{x:130,y:350,beat:8},{x:530,y:320,beat:9}];
  assert.equal(M.nearestAnchor(anchors,100,330).beat,8);assert.equal(M.nearestAnchor(anchors,510,120).beat,1);
});
test('approximate TAB geometry is carried into the UI', () => {
  const events=M.normalizeEvents([{pitch:64,start:'0',duration:'1/3'}]);
  assert.equal(M.anchorsFor(events,[{x:200,y:300,staff:1,approximate:true}],1000)[0].approximate,true);
});
test('invalid MIDI pitches and non-finite timing are rejected', () => {
  assert.equal(M.normalizeEvents([{pitch:130,start:0,duration:1},{pitch:60,start:'NaN',duration:1},{pitch:60,start:0,duration:0}]).length,0);
});
