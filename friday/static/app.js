const $ = id => document.getElementById(id);
let state, busy = false, signature = '';
const csrf = document.querySelector('meta[name="csrf"]').content;
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Friday-CSRF':csrf},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function notice(text) { $('notice').textContent = text; }
function element(tag, text, cls) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if(cls) el.className = cls; return el; }
function messages(items) {
  const next = JSON.stringify(items);
  if(next === signature) return;
  signature = next;
  if(!items.length) return;
  $('messages').replaceChildren();
  for(const item of items) { const row = element('div',undefined,`message ${item.role}`); row.append(element('b',item.role === 'user' ? 'YOU' : 'FRIDAY'),document.createTextNode(item.content)); if(item.role==='assistant'){const replay=element('button','▶ Speak','replay');replay.addEventListener('click',()=>FridayVoice.speak(item.content));row.prepend(replay);} $('messages').append(row); }
  $('messages').scrollTop = $('messages').scrollHeight;
}
function actions(items) {
  $('action-count').textContent = `${items.length} ACTIONS`;
  $('actions').replaceChildren();
  if(!items.length) { $('actions').append(element('p','Your tool calls and approval requests will appear here.','empty')); return; }
  for(const item of items) {
    const row = element('article',undefined,'action'), top = element('div',undefined,'action-top');
    top.append(element('strong',item.tool.replaceAll('_',' ')),element('span',item.status,`status ${item.status}`)); row.append(top);
    const detail = element('details'); detail.open = item.status === 'pending'; detail.append(element('summary','Arguments & result'),element('pre',JSON.stringify(item.args,null,2)+(item.result ? '\nResult: '+item.result : ''))); row.append(detail);
    if(item.status === 'pending') for(const [label,approve] of [['Approve',true],['Reject',false]]) {
      const button = element('button',label); button.addEventListener('click', async () => { button.disabled = true; try { await api(`/api/actions/${item.id}`,{approve}); await refresh(); } catch(error) { notice(error.message); button.disabled = false; } }); row.append(button);
    }
    $('actions').append(row);
  }
}
async function refresh() {
  try { state = await api('/api/state'); const s = state.system;
    $('host').textContent = s.host; $('os').textContent = s.os; $('cpu').textContent = `${s.cpu_count} CPU cores`; $('load').textContent = s.load_average ? `Load average · ${s.load_average.map(x=>x.toFixed(2)).join(' / ')}` : 'Load average unavailable'; $('disk').textContent = `${s.disk_used_gb} / ${s.disk_total_gb} GB`; $('model').textContent = s.model; $('workspace-path').textContent = s.workspace;
    $('app-name').replaceChildren(...s.apps.map(name => {const option=element('option',name); option.value=name; return option;}));
    messages(state.messages); actions(state.actions); $('camera-panel').hidden = !state.camera; if(state.camera && !$('camera').getAttribute('src')) $('camera').src='/video_feed';
  } catch(error) { notice(error.message); }
}
async function send(command) {
  if(busy || !command.trim()) return;
  FridayVoice.stop(); busy=true; $('send').disabled=true; $('task-status').textContent='Working on your instruction…'; notice('');
  try { const pending = [...(state?.messages || []),{role:'user',content:command}]; messages(pending); $('command').value=''; const result=await api('/api/command',{command}); FridayVoice.remember(result.spoken || result.speech); if($('speech').checked) FridayVoice.speak(result.spoken || result.speech); }
  catch(error) { notice(error.message); }
  finally { busy=false; $('send').disabled=false; $('task-status').textContent='Tools ready · approval for changes'; await refresh(); }
}
$('command-form').addEventListener('submit',event=>{event.preventDefault();send($('command').value);});
$('command').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send($('command').value);}});
document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>send(button.dataset.prompt)));
function toolFields() { const name=$('tool-select').value; $('path-field').hidden=!['read_file','write_file','list_files'].includes(name); $('content-field').hidden=name!=='write_file'; $('app-field').hidden=name!=='launch_app'; $('tool-hint').textContent=['write_file','launch_app'].includes(name)?'A proposal will appear in Activity for your approval.':'Read-only operation on the host machine.'; }
$('tool-select').addEventListener('change',toolFields); toolFields();
$('run-tool').addEventListener('click',async()=>{const button=$('run-tool');button.disabled=true;notice('');try{const name=$('tool-select').value,args={};if(['read_file','write_file','list_files'].includes(name))args.path=$('path').value;if(name==='write_file')args.content=$('content').value;if(name==='launch_app')args.name=$('app-name').value;await api('/api/tools',{name,arguments:args});await refresh();$('activity').scrollIntoView({behavior:'smooth'});}catch(error){notice(error.message);}finally{button.disabled=false;}});
let recognition;
$('mic').addEventListener('click',()=>{const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){notice('Voice input is unavailable in this browser. Use the text box.');return;}if(recognition){recognition.stop();return;}FridayVoice.stop(); recognition=new Recognition();recognition.lang='en-US';recognition.onresult=event=>{$('command').value=event.results[0][0].transcript;if($('voice-send').checked)send($('command').value);};recognition.onerror=event=>notice(`Microphone: ${event.error}. You can type your instruction.`);recognition.onend=()=>{recognition=null;$('mic').textContent='♩';};$('mic').textContent='■';try{recognition.start();}catch(error){recognition=null;notice(error.message);}});
document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',async()=>{try{await api('/api/vision/mode',{mode:button.dataset.mode});}catch(error){notice(error.message);}}));
$('analyze').addEventListener('click',async()=>{try{const result=await api('/api/analyze',{});notice(result.speech_text);}catch(error){notice(error.message);}});
function clock(){ $('clock').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}); } clock();setInterval(clock,1000);refresh();setInterval(()=>{if(!busy)refresh();},15000);
