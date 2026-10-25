// Independent parser used to verify exported note attacks and silent endings.
module.exports=function readMidi(buffer){
  if(buffer.subarray(0,4).toString()!=='MThd')throw new Error('Not MIDI');
  const ticks=buffer.readUInt16BE(12);let pos=22,tick=0,status=0;const notes=[],programs=[];
  const end=22+buffer.readUInt32BE(18);
  const vlq=()=>{let n=0,b;do{b=buffer[pos++];n=(n<<7)|(b&127);}while(b&128);return n;};
  while(pos<end){tick+=vlq();let s=buffer[pos];if(s&128){pos++;if(s<240)status=s;}else s=status;
    if(s===255){const type=buffer[pos++],size=vlq();pos+=size;if(type===47)return{ticks,notes,programs,end:tick};continue;}
    if(s===240||s===247){const length=vlq();pos+=length;continue;}
    const count=[192,208].includes(s&240)?1:2;const a=buffer[pos++],b=count===2?buffer[pos++]:0;
    if((s&240)===144&&b>0)notes.push([tick,a]);if((s&240)===192)programs.push(a);
  }
  throw new Error('Missing MIDI end');
};
