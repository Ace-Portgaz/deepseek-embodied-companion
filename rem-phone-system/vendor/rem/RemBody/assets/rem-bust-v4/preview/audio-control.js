// Mouth amplitude comes only from the PCM actually played by Web Audio.
export function createVoiceControl(renderer, button, label) {
  let ctx, analyser, source, playing=false, generation=0, raf=0, envelope=0;
  const audioUrl=new URL('./audio/lip-sync-test.wav',import.meta.url);
  function stop() {
    generation++;playing=false;cancelAnimationFrame(raf);try{source?.stop();}catch{}
    source?.disconnect();source=null;envelope=0;renderer.setVoice(0,false);
    button.textContent='试听口型联动';label.textContent='口型测试使用系统测试语音，不是角色原声。';
  }
  async function start() {
    stop();const token=++generation;
    ctx??=new AudioContext();await ctx.resume();
    const response=await fetch(audioUrl);if(!response.ok)throw Error('测试语音读取失败');
    const buffer=await ctx.decodeAudioData(await response.arrayBuffer());if(token!==generation)return;
    analyser=ctx.createAnalyser();analyser.fftSize=512;
    source=ctx.createBufferSource();source.buffer=buffer;source.connect(analyser);analyser.connect(ctx.destination);
    source.onended=()=>{if(token===generation)stop();};source.start();playing=true;
    button.textContent='停止试听';label.textContent='正在根据实际播放音频驱动口型…';
    const samples=new Float32Array(analyser.fftSize);
    function tick(){if(!playing)return;analyser.getFloatTimeDomainData(samples);let sum=0;for(const x of samples)sum+=x*x;
      const target=Math.min(1,Math.max(0,(Math.sqrt(sum/samples.length)-.009)*7));
      envelope+=(target-envelope)*(target>envelope?.8:.45);renderer.setVoice(envelope,true);raf=requestAnimationFrame(tick);}
    tick();
  }
  button.addEventListener('click',()=>{if(playing)stop();else start().catch(e=>{stop();label.textContent=e.message;});});
  return {stop,get playing(){return playing;}};
}
