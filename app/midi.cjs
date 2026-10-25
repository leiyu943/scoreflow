const Music = require('./music.cjs');
const INSTRUMENTS = [
  { program:24,name:'古典吉他' }, { program:25,name:'钢弦吉他' }, { program:27,name:'清音电吉他' },
  { program:0,name:'三角钢琴' }, { program:4,name:'电钢琴' }, { program:48,name:'弦乐合奏' }, { program:73,name:'长笛' }
];
function vlq(value) { let n=Math.max(0,Math.round(value)),a=[n&127];while(n>>=7)a.unshift((n&127)|128);return a; }
function makeMidi(events, meters, bpm, program=24, endBeat=null) {
  if(!INSTRUMENTS.some(i=>i.program===program))throw new Error('无效音色');
  const ticks=960, rows=[];
  for(const e of Music.normalizeEvents(events)){
    const start=Math.round(e.start*ticks),end=Math.max(start+1,Math.round((e.start+e.duration)*ticks));
    rows.push([start,1,[144,e.pitch,Math.max(1,Math.min(127,Math.round(e.velocity)))]],[end,0,[128,e.pitch,0]]);
  }
  for(const m of meters||[]){const [n,d]=m.meter;if(n>0&&n<256&&d>0&&(d&(d-1))===0)rows.push([Math.round(Music.rational(m.start)*ticks),-2,[255,88,4,n,Math.log2(d),24,8]]);}
  const tempo=Math.round(60000000/Math.max(20,Math.min(300,bpm||120)));
  const data=[0,255,81,3,(tempo>>16)&255,(tempo>>8)&255,tempo&255,0,192,program];let previous=0;
  rows.sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2][1]-b[2][1]);
  for(const [tick,_,bytes]of rows){data.push(...vlq(tick-previous),...bytes);previous=tick;}
  const finalTick=endBeat==null?previous:Math.max(previous,Math.round(Music.rational(endBeat)*ticks));
  data.push(...vlq(finalTick-previous),255,47,0);
  const header=Buffer.alloc(22);header.write('MThd',0);header.writeUInt32BE(6,4);header.writeUInt16BE(0,8);header.writeUInt16BE(1,10);header.writeUInt16BE(ticks,12);header.write('MTrk',14);header.writeUInt32BE(data.length,18);
  return Buffer.concat([header,Buffer.from(data)]);
}
module.exports={INSTRUMENTS,makeMidi};
