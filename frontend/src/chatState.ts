import type {Conversation,Job} from './types';

export const replyRunning=(job:Job|null)=>Boolean(job&&['queued','generating','writing','running'].includes(job.state));

/** The POST acknowledgement is enough to observe a job even if transcript fetch fails. */
export function watchedJobId(conversation:Conversation|null,job:Job|null,chatId:string):string|undefined{
 if(job?.chat_id===chatId&&replyRunning(job))return job.id;
 if(conversation?.id!==chatId)return;
 return typeof conversation.active_job==='string'?conversation.active_job:conversation.active_job?.id;
}

/** Polls and SSE arrive independently; neither may roll back an accepted snapshot. */
export function mergeConversation(current:Conversation|null,incoming:Conversation,chatId:string):Conversation|null{
 if(incoming.id!==chatId)return current;
 if(current?.id===incoming.id&&incoming.revision<current.revision)return current;
 return incoming;
}

export function mergeJob(current:Job|null,incoming:Job,chatId:string,jobId:string):Job|null{
 if(incoming.chat_id!==chatId||incoming.id!==jobId)return current;
 if(current?.id===incoming.id){
  if((incoming.sequence??0)<(current.sequence??0))return current;
  if(!replyRunning(current)&&replyRunning(incoming))return current;
  if(!replyRunning(current)&&incoming.state!==current.state)return current;
 }
 return incoming;
}

/** A repeated answer in an earlier turn is not acknowledgement of this reply. */
export function replyInTranscript(job:Job,conversation:Conversation|null):boolean{
 if(!conversation||job.chat_id!==conversation.id||job.state!=='completed')return false;
 // user_index is the durable turn identity; job.revision may also include a later rename.
 if(job.user_index===undefined&&(typeof job.revision!=='number'||conversation.revision<job.revision))return false;
 let index=job.user_index??-1;
 if(job.user_index===undefined)for(let i=conversation.messages.length-1;i>=0;i--)if(conversation.messages[i].role==='user'){index=i;break;}
 const question=conversation.messages[index],answer=conversation.messages[index+1];
 return index>=0&&question?.role==='user'&&question.content===job.question&&answer?.role==='assistant'&&answer.content===job.text;
}

export function completedReplyPending(job:Job|null,conversation:Conversation|null):boolean{
 return Boolean(job&&conversation&&job.chat_id===conversation.id&&job.state==='completed'&&job.verification?.passed===true&&job.text.trim()&&!replyInTranscript(job,conversation));
}

export function replyFailure(job:Job|null,conversation:Conversation|null){
 if(job?.chat_id!==conversation?.id)return conversation?.failure;
 if(replyRunning(job)||completedReplyPending(job,conversation))return null;
 if(job&&['failed','incomplete','cancelled'].includes(job.state)){
  if(conversation?.failure?.job_id===job.id)return conversation.failure;
  return {job_id:job.id,state:job.state,error:job.error,partial:job.text,verification:job.verification,retry_at:job.retry_at};
 }
 return conversation?.failure;
}
