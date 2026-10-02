import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createPronunciationController} from '../src/milai/web/pronunciation-controller.js';
import {renderMarkdown, renderPronunciationText, renderExerciseMarkdown} from '../src/milai/web/markdown.bundle.js';

const span = {id:'saved', locale:'de-DE', position:2, text:'Ich möchte einen Kaffee.'};
const control = (id='saved') => ({dataset:{spanId:id}, textContent:span.text, attrs:{}, listeners:{},
  setAttribute(key,value) {this.attrs[key]=value;}, addEventListener(key,value) {this.listeners[key]=value;}});
const scope = {session:'session', lesson_id:'lesson'};
const deferred = () => {let resolve, reject; const promise = new Promise((a,b) => {resolve=a; reject=b;}); return {promise,resolve,reject};};
function harness(fetchClip) {
  const audios = [];
  const controller = createPronunciationController({fetchClip, createURL:()=> 'blob:clip', revokeURL:()=>{},
    createAudio:()=> {const audio={pauses:0,plays:0,currentTime:2,pause(){this.pauses++;},async play(){this.plays++;}}; audios.push(audio); return audio;}});
  return {controller,audios};
}

test('whole phrase, punctuation, emphasis, Unicode and keyboard control render intact', () => {
  const html = renderMarkdown(`**${span.text}**`, [span]);
  assert.match(html, /<strong><span class="pronunciation" role="button" tabindex="0"/);
  assert.match(html, /Ich möchte einen Kaffee\.<\/span><\/strong>/);
  assert.equal((html.match(/class="pronunciation"/g)||[]).length, 1);
  const unicode = {id:'ru',locale:'ru-RU',position:2,text:'Привет!'};
  assert.match(renderPronunciationText('😀 Привет!', [unicode]), /^😀 <span/);
  const blank = renderExerciseMarkdown('Ich {{blank}} Kaffee.', [{...span,position:0,text:'Ich'},{...span,id:'after',position:14,text:'Kaffee.'}]);
  assert.match(blank, /exercise-blank/);
  assert.doesNotMatch(blank, /class="pronunciation"/);
});

test('no synthesis on binding; keyboard access, loading and repeated playback use memory', async () => {
  const wait = deferred(); let calls=0;
  const {controller,audios} = harness(async payload => {calls++; assert.equal(payload.span_id,'saved'); return wait.promise;});
  const button=control(); controller.bind({querySelectorAll:()=>[button]},scope);
  assert.equal(calls,0);
  let prevented=false;
  button.listeners.keydown({key:' ',preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  assert.equal(button.dataset.state,'loading');
  assert.equal(button.attrs['aria-busy'],'true');
  wait.resolve({}); await new Promise(resolve=>setImmediate(resolve));
  assert.equal(audios[0].plays,1);
  await controller.play(button,scope);
  assert.equal(calls,1);
  assert.equal(audios[0].pauses,1);
  assert.equal(audios[0].currentTime,0);
  await controller.close();
});

test('selection does not fetch, errors require another click and retries can succeed', async () => {
  let calls=0;
  const {controller} = harness(async()=> {calls++; if(calls===1) throw new Error('failed'); return {};});
  const button=control(); controller.bind({querySelectorAll:()=>[button]},scope);
  globalThis.getSelection = ()=>({isCollapsed:false});
  button.listeners.click(); assert.equal(calls,0);
  delete globalThis.getSelection;
  await controller.play(button,scope);
  assert.equal(button.dataset.state,'error');
  assert.match(button.dataset.message,/retry/);
  assert.equal(calls,1);
  await controller.play(button,scope);
  assert.equal(calls,2);
  assert.equal(button.dataset.state,'playing');
  await controller.close();
});

test('latest selection plays; navigation suppresses late responses', async () => {
  const first=deferred(), second=deferred();
  const {controller,audios}=harness(payload=>payload.span_id==='first'?first.promise:second.promise);
  const one=controller.play(control('first'),scope);
  const two=controller.play(control('second'),scope);
  second.resolve({}); await two;
  first.resolve({}); await one;
  assert.equal(audios.length,1);
  controller.stop(); assert.equal(audios[0].pauses,1);
  const late=deferred();
  const other=harness(()=>late.promise);
  const pending=other.controller.play(control(),scope);
  other.controller.stop(); late.resolve({}); await pending;
  assert.equal(other.audios.length,0);
  await controller.close(); await other.controller.close();
});

test('browser playback restriction retains clip for another play click', async () => {
  let calls=0, plays=0;
  const controller=createPronunciationController({fetchClip:async()=>{calls++;return {};},createURL:()=> 'blob:clip',revokeURL:()=>{},
    createAudio:()=>({pause(){},async play(){plays++; if(plays===1) throw Object.assign(new Error('blocked'),{name:'NotAllowedError'});}})});
  const button=control(); await controller.play(button,scope);
  assert.equal(button.dataset.state,'error'); assert.match(button.dataset.message,/Audio ready/);
  await controller.play(button,scope);
  assert.equal(calls,1); assert.equal(plays,2);
  await controller.close();
});


test('annotated code examples retain clean selectable text and playback controls', () => {
  for (const [source, position] of [['`Ich lerne.`',1],['```\nIch lerne.\n```',4]]) {
    const html=renderMarkdown(source,[{...span,position,text:'Ich lerne.'}]);
    assert.match(html, /<code><span class="pronunciation"/);
    assert.match(html, /Ich lerne\.<\/span>/);
    assert.doesNotMatch(html, /[\uE000\uE001]/);
  }
});
