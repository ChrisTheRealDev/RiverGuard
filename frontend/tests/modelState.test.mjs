import test from 'node:test';
import assert from 'node:assert/strict';
import {modelActions,reconcileModelChoice} from '../src/modelState.ts';

const inventory={selected_model:'llama3.2:3b',revision:1,models:[{name:'llama3.2:3b'},{name:'qwen3.5:4b'}],loaded:[],active_jobs:0,warming:false,warm_error:null};

test('polling and a conflict refresh preserve an unapplied installed model choice',()=>{
 const draft={value:'qwen3.5:4b',dirty:true};
 assert.equal(reconcileModelChoice(draft,'llama3.2:3b'),draft);
 assert.equal(reconcileModelChoice(draft,'a-model-selected-by-another-browser'),draft);
 assert.equal(modelActions(inventory,draft.value).canSave,true);
 assert.equal(modelActions(inventory,draft.value).canPrepare,false);
 assert.deepEqual(reconcileModelChoice({value:'old',dirty:false},'qwen3.5:4b'),{value:'qwen3.5:4b',dirty:false});
});

test('active replies and model preparation block both switching and another warmup',()=>{
 for(const state of [{...inventory,active_jobs:1},{...inventory,warming:true}]){
  assert.deepEqual(modelActions(state,'qwen3.5:4b'),{locked:true,installed:true,canSave:false,canPrepare:false});
 }
});

test('missing model files cannot be selected or prepared through the app',()=>{
 assert.equal(modelActions({...inventory,models:[]},'qwen3.5:4b').canSave,false);
 assert.equal(modelActions({...inventory,models:[]},'qwen3.5:4b').canPrepare,false);
 assert.equal(modelActions(inventory,'llama3.2:3b').canSave,false);
 assert.equal(modelActions(inventory,'llama3.2:3b').canPrepare,true);
});
