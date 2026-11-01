// Speech stays on the host with Piper; browser voices are an explicit fallback.
window.FridayVoice = (() => {
  const get = id => document.getElementById(id);
  let generation = 0, controller, player, objectUrl, lastReply = '', currentUtterance;
  let selected = 'neural', rate = 1, neuralReady = false;
  const synth = window.speechSynthesis;
  function read(key, fallback) { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, value); } catch { /* Private mode still supports speech. */ } }
  selected = read('friday.voice', 'neural');
  rate = Math.max(.75, Math.min(1.25, Number(read('friday.rate', '1')) || 1));
  function status(text, mode) { get('voice-state').textContent = text; get('voice-orb').classList.toggle('speaking',mode==='speaking'); get('voice-orb').classList.toggle('thinking',mode==='loading'); }
  function releaseAudio() { if(player) { player.pause(); player.removeAttribute('src'); player.load(); player = null; } if(objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; } }
  function stop() { generation++; controller?.abort(); controller=null; releaseAudio(); synth?.cancel(); currentUtterance = null; status('Ready'); }
  function options() {
    const select=get('voice-select'); select.replaceChildren();
    const add=(value,label)=>{const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);};
    if(neuralReady) add('neural','British · local neural');
    if(synth) { add('browser','Browser default'); for(const voice of synth.getVoices()) add(`browser:${voice.voiceURI}`,`${voice.name} · ${voice.lang}`); }
    if(!select.options.length) add('unavailable','No voice available');
    if([...select.options].some(option=>option.value===selected)) select.value=selected;
    else { select.value=neuralReady?'neural':select.options[0].value; }
    detail();
  }
  function detail() { get('voice-detail').textContent = get('voice-select').value==='neural' ? 'Local neural voice · British English · text stays on this host' : 'Browser speech · voice availability and processing depend on your browser'; }
  function browserSpeak(text, ticket) {
    if(!synth) { status('No browser voice available'); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    const choice=get('voice-select').value;
    const voices=synth.getVoices();
    utterance.voice=voices.find(voice=>`browser:${voice.voiceURI}`===choice) || voices.find(voice=>voice.lang==='en-GB') || null;
    utterance.lang=utterance.voice?.lang || 'en-GB'; utterance.rate=rate; utterance.pitch=.95;
    currentUtterance=utterance;
    utterance.onstart=()=>{if(ticket===generation)status('Speaking','speaking');};
    utterance.onend=()=>{if(ticket===generation){currentUtterance=null;status('Ready');}};
    utterance.onerror=event=>{if(ticket===generation && event.error!=='canceled')status('Speech unavailable · try another voice');};
    synth.speak(utterance);
  }
  async function speak(text) {
    stop();
    if(!text?.trim())return;
    lastReply=text;
    const ticket=generation;
    const clean=text.replace(/```[\s\S]*?```/g,' Code is shown in the console. ').replace(/[*#`]/g,'').slice(0,1900);
    if(get('voice-select').value!=='neural') { browserSpeak(clean,ticket); return; }
    controller=new AbortController();
    status('Preparing voice…','loading');
    try {
      const response=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Friday-CSRF':document.querySelector('meta[name="csrf"]').content},body:JSON.stringify({text:clean,rate}),signal:controller.signal});
      if(!response.ok) { const result=await response.json(); throw new Error(result.error || 'Voice service unavailable'); }
      const blob=await response.blob(); if(ticket!==generation)return;
      objectUrl=URL.createObjectURL(blob); player=new Audio(objectUrl);
      player.onplaying=()=>{if(ticket===generation)status('Speaking','speaking');};
      player.onended=()=>{if(ticket===generation){releaseAudio();status('Ready');}};
      player.onerror=()=>{if(ticket===generation){releaseAudio();status('Audio playback failed · try Preview voice');}};
      await player.play();
    } catch(error) {
      if(ticket!==generation || error.name==='AbortError')return;
      releaseAudio(); status(error.name==='NotAllowedError'?'Press Replay reply to allow audio':'Neural voice unavailable · choose a browser voice');
    }
  }
  get('voice-select').addEventListener('change',()=>{stop();selected=get('voice-select').value;save('friday.voice',selected);detail();});
  get('voice-rate').value=rate;get('rate-label').textContent=`${rate.toFixed(2)}×`;
  get('voice-rate').addEventListener('input',()=>{rate=Number(get('voice-rate').value);get('rate-label').textContent=`${rate.toFixed(2)}×`;save('friday.rate',String(rate));});
  get('speech').checked=read('friday.speech','true')==='true';
  get('speech').addEventListener('change',()=>{save('friday.speech',String(get('speech').checked));if(!get('speech').checked)stop();});
  get('voice-preview').addEventListener('click',()=>speak('Good evening. FRIDAY at your service. Systems are ready. What shall we work on?'));
  get('voice-stop').addEventListener('click',stop);
  get('voice-replay').addEventListener('click',()=>{if(lastReply)speak(lastReply);else status('Send an instruction or preview a voice first');});
  synth?.addEventListener('voiceschanged',options);
  options();
  fetch('/api/voice').then(response=>response.ok?response.json():null).then(data=>{neuralReady=Boolean(data?.available);options();if(data && !data.available)get('voice-detail').textContent=data.message;}).catch(()=>status('Local voice status unavailable'));
  window.addEventListener('pagehide',stop);
  return {speak,stop,remember(text){lastReply=text;}};
})();
