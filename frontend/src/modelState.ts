export type InstalledModel={name:string;size:number;parameter_size?:string;quantization_level?:string;thinking?:boolean};
export type ModelInventory={selected_model:string;revision:number;provider:{label:string;model:string;local:boolean;host:string};models:InstalledModel[];loaded:{name:string;processor:'CPU'|'GPU'|'CPU + GPU'}[];active_jobs:number;warming:boolean;warm_error:string|null};
export type ModelChoice={value:string;dirty:boolean};

export function reconcileModelChoice(choice:ModelChoice,selected:string):ModelChoice{
 return choice.dirty?choice:{value:selected,dirty:false};
}
export function modelListPlaceholder(everLoaded:boolean,initialLoadInFlight:boolean):string{
 return !everLoaded&&initialLoadInFlight?'Checking installed models…':'Choose an installed model';
}
export function modelActions(info:ModelInventory|null,choice:string){
 const installed=Boolean(info?.models.some(model=>model.name===choice));
 const selectedInstalled=Boolean(info?.models.some(model=>model.name===info.selected_model));
 const locked=!info||info.active_jobs>0||info.warming;
 return {locked,installed,canSave:!locked&&installed&&choice!==info?.selected_model,canPrepare:!locked&&selectedInstalled&&choice===info?.selected_model};
}
