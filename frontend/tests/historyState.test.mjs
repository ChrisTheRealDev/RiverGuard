import test from 'node:test';
import assert from 'node:assert/strict';
import {historyTabForKey} from '../src/historyState.ts';

test('history keyboard navigation wraps and supports first and last tab',()=>{
 assert.equal(historyTabForKey('readings','ArrowLeft'),'evidence');
 assert.equal(historyTabForKey('evidence','ArrowRight'),'readings');
 assert.equal(historyTabForKey('readings','ArrowRight'),'alerts');
 assert.equal(historyTabForKey('evidence','ArrowLeft'),'alerts');
 assert.equal(historyTabForKey('alerts','Home'),'readings');
 assert.equal(historyTabForKey('readings','End'),'evidence');
 assert.equal(historyTabForKey('alerts','Tab'),null);
 assert.equal(historyTabForKey('alerts','ArrowDown'),null);
});
