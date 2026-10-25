const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {dialog}=require('electron');
const readMidi=require('./midi-reader.cjs');

module.exports=async function({win,js,check,soundReady,base,checks,delay}){
  const files=JSON.parse(process.env.SCOREFLOW_TEST_MULTIPAGE);
  const open=dialog.showOpenDialog;
  dialog.showOpenDialog=async()=>({canceled:false,filePaths:files});
  let imported;
  try{imported=await js(`window.scoreflow.openImage()`);assert.ok(imported.ok,imported.error);}finally{dialog.showOpenDialog=open;}
  await js(`ScoreFlowView.displayImage(${JSON.stringify(imported.value)})`);
  await check('multi-select imports three pages in natural numeric order',`ScoreFlowView.state.pages.length===3 && ScoreFlowView.state.pages.map(p=>p.name).join(',')==='page-1.png,page-2.png,page-10.png'`);
  await js(`window.__batchProgress=[];window.__cancelOnce=true;window.scoreflow.onProgress(p=>{window.__batchProgress.push(p);if(window.__cancelOnce&&p.stage==='page-done'&&p.pageIndex===0){window.__cancelOnce=false;window.scoreflow.cancel();}});void 0`);
  const cancelled=await js(`window.scoreflow.recognize({mode:'auto',meter:'auto'})`);
  assert.equal(cancelled.ok,false);assert.match(cancelled.error,/取消/);checks.push('multi-page cancellation stops without exporting an incomplete piece');
  await js(`window.__batchProgress=[]`);
  const response=await js(`window.scoreflow.recognize({mode:'auto',meter:'auto'})`);
  assert.ok(response.ok,response.error);assert.equal(response.value.pages.length,3);
  await check('retry reuses the completed first page instead of launching its model again',`!window.__batchProgress.some(p=>p.pageIndex===0&&['staff','tab'].includes(p.stage))`);
  await check('remaining pages are really inferred sequentially',`window.__batchProgress.some(p=>p.pageIndex===1&&p.stage==='tab')&&window.__batchProgress.some(p=>p.pageIndex===2&&p.stage==='staff')`);
  await js(`ScoreFlowView.displayResult(${JSON.stringify(response.value)})`);await soundReady();
  await check('three pages share one global MIDI timeline',`ScoreFlowView.state.pages.length===3 && ScoreFlowView.state.pages[1].start>0 && ScoreFlowView.state.pages[2].start>ScoreFlowView.state.pages[1].start && ScoreFlowView.state.duration>ScoreFlowView.state.pages[2].start`);
  await js(`ScoreFlowView.seekTo(ScoreFlowView.state.pages[1].start+.1,true)`);await delay(120);
  await check('playing the second page switches the displayed sheet automatically',`ScoreFlowView.state.playing&&ScoreFlowView.state.currentPage===1&&ScoreFlowView.player.voices.size>0`);
  await js(`(async()=>{await ScoreFlowView.seekTo(ScoreFlowView.state.pages[1].start-.12,true);window.__continuousVoice=[...ScoreFlowView.player.voices][0];})()`);await delay(300);
  await check('continuous playback crosses a page boundary without restarting its audio source',`ScoreFlowView.state.playing&&ScoreFlowView.state.currentPage===1&&ScoreFlowView.player.voices.has(window.__continuousVoice)`);
  await js(`document.getElementById('page-select').value='2';document.getElementById('page-select').dispatchEvent(new Event('change'))`);
  await check('manual page browsing preserves the complete piece',`ScoreFlowView.state.currentPage===2&&!ScoreFlowView.state.playing&&Math.abs(ScoreFlowView.state.beat-ScoreFlowView.state.pages[2].start)<.001`);
  await js(`(()=>{const a=ScoreFlowView.state.anchors[0];window.__pageClickedBeat=a.beat;const el=document.getElementById('score-overlay'),r=el.getBoundingClientRect();el.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left+a.x*r.width/1920,clientY:r.top+a.y*r.width/1920}));})()`);await delay(100);
  await check('third-page score clicks seek to the corresponding global MIDI beat',`ScoreFlowView.state.playing&&ScoreFlowView.state.currentPage===2&&ScoreFlowView.state.beat>=window.__pageClickedBeat&&ScoreFlowView.state.beat<window.__pageClickedBeat+.4`);
  await js(`document.getElementById('play').click()`);
  win.show();win.focus();await delay(350);
  await fs.writeFile(path.join(base,'multi-page-piece.png'),(await win.webContents.capturePage()).toPNG());
  const midiPath=path.join(base,'complete-piece.mid'),save=dialog.showSaveDialog;
  dialog.showSaveDialog=async()=>({canceled:false,filePath:midiPath});
  try{const exported=await js(`window.scoreflow.exportFile('midi',24)`);assert.ok(exported.ok,exported.error);}finally{dialog.showSaveDialog=save;}
  const midi=readMidi(await fs.readFile(midiPath));
  const expected=response.value.events.map(e=>[Math.round(e.start*midi.ticks),e.pitch]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  assert.deepEqual(midi.notes.sort((a,b)=>a[0]-b[0]||a[1]-b[1]),expected);
  assert.equal(midi.end,Math.round(response.value.duration*midi.ticks));checks.push('exported whole-piece MIDI includes all pages and exact trailing silence');
  await js(`window.__batchProgress=[]`);
  const ids=response.value.pages.map(p=>p.id),reordered=[ids[2],ids[0],ids[1]];
  const edit=await js(`window.scoreflow.editPages(${JSON.stringify(reordered)})`);assert.ok(edit.ok,edit.error);
  await js(`ScoreFlowView.displayImage(${JSON.stringify(edit.value)})`);
  const rebuilt=await js(`window.scoreflow.recognize({mode:'auto',meter:'auto'})`);assert.ok(rebuilt.ok,rebuilt.error);
  assert.equal(rebuilt.value.pages[0].name,'page-10.png');checks.push('reordering pages changes the whole-piece order');
  await check('reordering recognized pages rebuilds the piece without running any model again',`!window.__batchProgress.some(p=>['staff','tab'].includes(p.stage))`);
  await js(`ScoreFlowView.displayResult(${JSON.stringify(rebuilt.value)})`);await soundReady();
  await fs.writeFile(path.join(base,'multi-page-reordered.png'),(await win.webContents.capturePage()).toPNG());
  // Append only one new page; all three previous page caches must remain valid.
  dialog.showOpenDialog=async()=>({canceled:false,filePaths:[files[0]]});
  let appended;
  try{appended=await js(`window.scoreflow.openImage(true)`);assert.ok(appended.ok,appended.error);}finally{dialog.showOpenDialog=open;}
  assert.equal(appended.value.pages.length,4);checks.push('append preserves the existing ordered pages and their recognition caches');
  await js(`ScoreFlowView.displayImage(${JSON.stringify(appended.value)});window.__batchProgress=[]`);
  const extended=await js(`window.scoreflow.recognize({mode:'auto',meter:'auto'})`);assert.ok(extended.ok,extended.error);
  assert.equal(extended.value.pages.length,4);
  await check('appending infers only the newly added page',`window.__batchProgress.some(p=>p.pageIndex===3&&['staff','tab'].includes(p.stage))&&!window.__batchProgress.some(p=>p.pageIndex<3&&['staff','tab'].includes(p.stage))`);
  await js(`ScoreFlowView.displayResult(${JSON.stringify(extended.value)})`);await soundReady();
  await fs.writeFile(path.join(base,'multi-page-appended.png'),(await win.webContents.capturePage()).toPNG());
  await fs.writeFile(path.join(base,'multi-page-result-summary.json'),JSON.stringify({pageCount:response.value.pages.length,events:response.value.events.length,duration:response.value.duration,pages:response.value.pages.map(p=>({name:p.name,start:p.start,duration:p.duration})),midiNotes:midi.notes.length,midiEndTicks:midi.end},null,2));
};
