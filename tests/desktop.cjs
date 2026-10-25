// Integration tests run inside an actual sandboxed Electron BrowserWindow.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { dialog } = require('electron');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function run({ win, app, importImage, presentResult, adoptResult }) {
  const checks = [], errors = [];
  win.webContents.on('console-message', event => { if (event.level === 'error') errors.push(event.message); });
  const js = code => win.webContents.executeJavaScript(code, true);
  const soundReady=async()=>{for(let i=0;i<120;i++){if(await js(`!!ScoreFlowView.player.sample && !ScoreFlowView.state.soundLoading`))return;await delay(100);}throw new Error('Sample audio did not become ready');};
  const check = async (name, code) => { assert.ok(await js(code), name); checks.push(name); };
  const base = process.env.SCOREFLOW_TEST_OUTPUT || path.join(app.getPath('temp'), 'scoreflow-desktop-tests');
  await fs.mkdir(base, { recursive: true });
  try {
    await delay(600);
    await check('sandbox hides Node require', `typeof require === 'undefined' && typeof window.scoreflow.openImage === 'function'`);
    await check('three recognition modes exist', `[...document.getElementById('mode').options].map(o=>o.value).join(',') === 'auto,staff,tab'`);
    await check('empty workspace cannot export', `document.getElementById('export-top').disabled && document.getElementById('play').disabled`);
    await fs.writeFile(path.join(base,'welcome.png'),(await win.webContents.capturePage()).toPNG());
    await js(`document.getElementById('demo').click()`); await delay(400);
    await soundReady();
    await check('seven sampled instruments are available',`document.getElementById('instrument').options.length===7 && ScoreFlowView.player.sample.duration>1`);
    await js(`window.__firstSample=ScoreFlowView.player.sample.getChannelData(0).slice(4000,5000).reduce((s,v)=>s+Math.abs(v),0);document.getElementById('instrument').value='0';document.getElementById('instrument').dispatchEvent(new Event('change'));`);
    await soundReady();
    await check('piano selection loads a different sampled waveform',`Math.abs(ScoreFlowView.player.sample.getChannelData(0).slice(4000,5000).reduce((s,v)=>s+Math.abs(v),0)-window.__firstSample)>.01`);
    for(const program of [25,27,4,48,73]){
      await js(`document.getElementById('instrument').value='${program}';document.getElementById('instrument').dispatchEvent(new Event('change'))`);await soundReady();
      await check(`sample instrument ${program} renders and decodes`, `ScoreFlowView.player.sample.numberOfChannels===2 && ScoreFlowView.player.sample.duration>1`);
    }
    await js(`document.getElementById('tempo').value=90;document.getElementById('tempo').dispatchEvent(new Event('change'))`);await soundReady();
    await js(`ScoreFlowView.seekTo(0,true)`);await delay(60);
    await check('tempo changes preserve pitch with freshly rendered samples',`ScoreFlowView.player.sampleBpm===90 && [...ScoreFlowView.player.voices][0].playbackRate.value===1`);
    await js(`ScoreFlowView.player.stop();document.getElementById('tempo').value=108;document.getElementById('instrument').value='24';document.getElementById('instrument').dispatchEvent(new Event('change'))`);await soundReady();
    await check('demo is clearly labelled', `ScoreFlowView.state.demo && !document.getElementById('demo-notice').hidden && document.getElementById('export-top').disabled`);
    await check('piano roll and score anchors are loaded', `ScoreFlowView.state.events.length===16 && ScoreFlowView.state.anchors.length===16 && !document.getElementById('roll-empty').hidden===false`);
    await js(`ScoreFlowView.seekTo(8,true)`); await delay(150);
    await check('seeking starts actual Web Audio voices', `ScoreFlowView.state.playing && ScoreFlowView.state.beat>=8 && ScoreFlowView.player.voices.size>0 && ScoreFlowView.player.context.state==='running'`);
    await js(`ScoreFlowView.player.stop(); document.getElementById('play').click()`); await delay(100);
    await check('play toggle resumes', `ScoreFlowView.state.playing`);
    await js(`ScoreFlowView.player.stop();`);
    await fs.writeFile(path.join(base,'demo.png'),(await win.webContents.capturePage()).toPNG());
    const fixtures = process.env.SCOREFLOW_TEST_RESULTS ? JSON.parse(process.env.SCOREFLOW_TEST_RESULTS) : [];
    for (let i=0;i<fixtures.length;i++) {
      const raw=JSON.parse(await fs.readFile(fixtures[i],'utf8'));
      await importImage(raw.source_image || raw.image);
      adoptResult(raw);
      const data=await presentResult(raw);
      await js(`ScoreFlowView.displayResult(${JSON.stringify(data)})`);await soundReady();await delay(150);
      await check(`actual result ${i+1}: MIDI visualization and anchors`, `ScoreFlowView.state.events.length>0 && ScoreFlowView.state.anchors.length>0 && !document.getElementById('export-top').disabled`);
      await js(`ScoreFlowView.seekTo(ScoreFlowView.state.anchors[Math.floor(ScoreFlowView.state.anchors.length/2)].beat,true)`);await delay(130);
      await check(`actual result ${i+1}: playback after seek`, `ScoreFlowView.state.playing && ScoreFlowView.player.context.state==='running'`);
      await js(`ScoreFlowView.player.stop()`);
      await js(`(() => { const s=ScoreFlowView.state; const a=s.anchors[Math.floor(s.anchors.length*.75)]; window.__clickedBeat=a.beat; const el=document.getElementById('score-overlay');const r=el.getBoundingClientRect();el.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left+a.x*r.width/1920,clientY:r.top+a.y*r.width/1920})); })()`);
      await delay(110);
      await check(`actual result ${i+1}: clicking score resolves MIDI onset`, `ScoreFlowView.state.playing && ScoreFlowView.state.beat>=window.__clickedBeat && ScoreFlowView.state.beat<window.__clickedBeat+.4`);
      await js(`document.getElementById('play').click()`); await delay(50);
      if(data.pages?.length>1){
        await js(`(async()=>{await ScoreFlowView.seekTo(ScoreFlowView.state.pages[1].start-.12,true);window.__boundaryVoice=[...ScoreFlowView.player.voices][0];})()`);await delay(300);
        await check(`actual result ${i+1}: continuous automatic page turn keeps the same audio source`,`ScoreFlowView.state.playing&&ScoreFlowView.state.currentPage===1&&ScoreFlowView.player.voices.has(window.__boundaryVoice)`);
        await js(`document.getElementById('play').click()`);
      }
      await fs.writeFile(path.join(base,`recognized-${i+1}.png`),(await win.webContents.capturePage()).toPNG());
    }
    if (process.env.SCOREFLOW_TEST_IMAGE) {
      await importImage(process.env.SCOREFLOW_TEST_IMAGE);
      const response=await js(`window.scoreflow.recognize({mode:'auto',meter:'auto'})`);
      assert.ok(response.ok,response.error);checks.push('actual IPC recognition completes and saves MIDI');
      await js(`ScoreFlowView.displayResult(${JSON.stringify(response.value)})`);
      await soundReady();
      const save=dialog.showSaveDialog;
      const midi=path.join(base,'exported-by-desktop.mid');
      dialog.showSaveDialog=async()=>({canceled:false,filePath:midi});
      try { const exported=await js(`window.scoreflow.exportFile('midi',0)`);assert.ok(exported.ok,exported.error); }
      finally { dialog.showSaveDialog=save; }
      const file=await fs.readFile(midi);assert.equal(file.subarray(0,4).toString(),'MThd');assert.equal(file[31],0);checks.push('MIDI Save As creates real MIDI file with selected piano instrument');
      const xml=path.join(base,'exported-by-desktop.musicxml');dialog.showSaveDialog=async()=>({canceled:false,filePath:xml});
      try { const exported=await js(`window.scoreflow.exportFile('musicxml')`);assert.ok(exported.ok,exported.error); }
      finally { dialog.showSaveDialog=save; }
      assert.match(await fs.readFile(xml,'utf8'),/score-partwise/);checks.push('MusicXML Save As creates score');
      await fs.writeFile(path.join(base,'desktop-recognized.png'),(await win.webContents.capturePage()).toPNG());
    }
    if(process.env.SCOREFLOW_TEST_MULTIPAGE)await require('./multipage-desktop.cjs')({win,js,check,soundReady,base,checks,delay});
    assert.deepEqual(errors,[],'renderer console errors');
    await fs.writeFile(path.join(base,'desktop-tests.json'),JSON.stringify({passed:true,checks,rendererErrors:errors},null,2));
    console.log(JSON.stringify({passed:true,checks:checks.length,output:base}));
    app.exit(0);
  } catch(error) {
    await fs.writeFile(path.join(base,'failure.png'),(await win.webContents.capturePage()).toPNG());
    await fs.writeFile(path.join(base,'desktop-tests.json'),JSON.stringify({passed:false,checks,error:error.stack,rendererErrors:errors},null,2));
    console.error(error.stack);app.exit(1);
  }
}
module.exports={run};
