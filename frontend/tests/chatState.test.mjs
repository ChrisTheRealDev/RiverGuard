import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeConversation,mergeJob,replyInTranscript,completedReplyPending,watchedJobId,replyFailure,shouldFollowReply} from '../src/chatState.ts';

const question={role:'user',content:'What does pH mean?'};
const answer={role:'assistant',content:'A pH of 7 is neutral.'};
const conversation={id:'chat-a',source:'simulation',title:'River',revision:2,messages:[question],active_job:'job-a'};
const generating={id:'job-a',chat_id:'chat-a',state:'generating',text:'A pH of 7',sequence:4,revision:2,question:question.content,user_index:0};
const completed={...generating,state:'completed',text:answer.content,sequence:5,revision:3,verification:{passed:true,reasons:[],can_continue:true}};
const canonical={...conversation,revision:3,messages:[question,answer],active_job:null};
const visibleAnswers=(job,chat)=>chat.messages.filter(m=>m.role==='assistant').length+Number(completedReplyPending(job,chat));

test('empty chats keep the welcome visible while replies follow only readers at the bottom',()=>{
 assert.equal(shouldFollowReply(0,null,false,true),false);
 assert.equal(shouldFollowReply(1,null,false,true),true);
 assert.equal(shouldFollowReply(0,generating,false,true),true);
 assert.equal(shouldFollowReply(1,generating,false,false),false);
 assert.equal(shouldFollowReply(1,generating,true,true),false);
});

test('a completed reply remains visible during delayed or failed transcript refresh, then appears exactly once',()=>{
 let chat=conversation,job=generating;
 job=mergeJob(job,completed,'chat-a','job-a');
 assert.equal(visibleAnswers(job,chat),1);
 // A failed GET changes no snapshot; an older successful poll must not hide the completed text.
 chat=mergeConversation(chat,{...conversation,revision:1},'chat-a');
 assert.equal(visibleAnswers(job,chat),1);
 chat=mergeConversation(chat,canonical,'chat-a');
 assert.equal(visibleAnswers(job,chat),1);
 assert.equal(completedReplyPending(job,chat),false);
 chat=mergeConversation(chat,conversation,'chat-a');
 assert.equal(chat.revision,3);
 assert.equal(visibleAnswers(job,chat),1);
});

test('out-of-order job events cannot roll back text or resurrect a finished generation',()=>{
 assert.equal(mergeJob(generating,{...generating,text:'A',sequence:3},'chat-a','job-a'),generating);
 assert.equal(mergeJob(completed,generating,'chat-a','job-a'),completed);
 assert.equal(mergeJob(completed,{...generating,sequence:6},'chat-a','job-a'),completed);
 const next={...generating,id:'job-b',sequence:1};
 assert.equal(mergeJob(next,completed,'chat-a','job-b'),next);
});

test('an identical answer in an earlier turn does not acknowledge the latest reply',()=>{
 const latest={...completed,id:'job-b',user_index:2,revision:5};
 const before={...conversation,revision:4,messages:[question,answer,question]};
 assert.equal(replyInTranscript(latest,before),false);
 assert.equal(completedReplyPending(latest,before),true);
 const after={...before,revision:5,messages:[question,answer,question,answer]};
 assert.equal(replyInTranscript(latest,after),true);
 assert.equal(visibleAnswers(latest,after),2);
});

test('exact turn acknowledgement survives a later rename or new turn advancing job metadata revision',()=>{
 assert.equal(replyInTranscript({...completed,revision:20},canonical),true);
 const later={...canonical,revision:4,messages:[question,answer,{role:'user',content:'A later question'}]};
 assert.equal(replyInTranscript(completed,later),true);
 assert.equal(completedReplyPending(completed,later),false);
});

test('responses from another conversation cannot overwrite state or leak a completed reply',()=>{
 const other={...conversation,id:'chat-b'};
 assert.equal(mergeConversation(other,canonical,'chat-b'),other);
 assert.equal(mergeJob(null,completed,'chat-b','job-a'),null);
 assert.equal(completedReplyPending(completed,other),false);
});

test('incomplete and unverified replies never appear as a completed fallback',()=>{
 assert.equal(completedReplyPending({...completed,state:'incomplete'},conversation),false);
 assert.equal(completedReplyPending({...completed,verification:{passed:false,reasons:['Unsupported claim'],can_continue:false}},conversation),false);
 assert.equal(completedReplyPending({...completed,verification:null},conversation),false);
});

test('POST acknowledgement starts observation even when the first conversation GET fails',()=>{
 const before={...conversation,active_job:null};
 const queued={...generating,state:'queued',sequence:1};
 assert.equal(watchedJobId(before,queued,'chat-a'),'job-a');
 const finished=mergeJob(queued,completed,'chat-a',watchedJobId(before,queued,'chat-a'));
 assert.equal(completedReplyPending(finished,before),true);
 assert.equal(watchedJobId(before,queued,'chat-b'),undefined);
});

test('a new accepted job suppresses the prior failure; terminal failure retains its own partial until sync',()=>{
 const oldFailure={...conversation,failure:{job_id:'old-job',partial:'Old unverified reply',error:'Old error'}};
 assert.equal(replyFailure(generating,oldFailure),null);
 assert.equal(replyFailure(completed,oldFailure),null);
 const failed={...generating,state:'incomplete',text:answer.content,error:'Unverified',verification:{passed:false,reasons:['Unsupported'],can_continue:false}};
 const withIdenticalEarlierAnswer={...oldFailure,messages:[question,answer,question]};
 const failure=replyFailure(failed,withIdenticalEarlierAnswer);
 assert.equal(failure.job_id,'job-a');
 assert.equal(failure.partial,answer.content);
 assert.equal(failure.verification.passed,false);
 assert.equal(failure.verification.can_continue,false);
 assert.equal(completedReplyPending(failed,withIdenticalEarlierAnswer),false);
});
