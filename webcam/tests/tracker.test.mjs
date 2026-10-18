import test from 'node:test';import assert from 'node:assert/strict';import {RepeatTracker} from '../presentation/tracker.mjs';
const item=(title='Black backpack',bbox=[.1,.1,.2,.3])=>({title,color:'Black',bbox});
test('one sighting remains a candidate; consecutive overlap repeats',()=>{const t=new RepeatTracker();assert.equal(t.update([item()])[0].repeated,false);assert.equal(t.update([item('Black backpack',[.12,.1,.2,.3])])[0].repeated,true);});
test('same color never conflates different types',()=>{const t=new RepeatTracker();t.update([item()]);assert.equal(t.update([item('Black laptop')])[0].repeated,false);});
test('empty or distant views break consecutive evidence',()=>{const t=new RepeatTracker();t.update([item()]);t.update([]);assert.equal(t.update([item()])[0].repeated,false);assert.equal(t.update([item('Black backpack',[.7,.6,.2,.3])])[0].repeated,false);});
test('multiple identical objects cannot reuse one track in the same scan',()=>{const t=new RepeatTracker();t.update([item()]);const items=t.update([item(),item()]);assert.equal(items.filter(d=>d.repeated).length,1);assert.notEqual(items[0].track_id,items[1].track_id);});
