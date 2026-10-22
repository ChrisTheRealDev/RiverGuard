export {};
export interface Reading {
 id:number|string|null;station_id:string;device_id:string;source:'simulation'|'esp32';timestamp:string|null;received_at:string|null;receivedAt:string|null;revision:number|null;
 values:Record<'ph'|'turbidity'|'temperature'|'water_level',number|null>;ph:number|null;turbidity:number|null;temperature:number|null;water_level:number|null;
 raw:Record<string,unknown>;health:Record<string,string>;sensor_health:Record<string,string>;settings:any;payload:any;calibrated:boolean;provisional:boolean;fresh:boolean;age_seconds:number|null;connection_age_seconds:number|null;clock_ahead:boolean;calibration_label:string;
}
export interface Signal {lastKnown?:boolean;kind:string;severity:'Review'|'Watch'|'Warning';title:string;explanation:string;timestamp:string|null}
export interface Evaluation {latest:Reading|null;previous:Reading|null;deltas:Partial<Record<'ph'|'turbidity'|'temperature'|'water_level',number>>;signals:Signal[];rate:number|null;missing:string[];settings:{elevated:number;warning:number;rise_limit:number};tone:string;title:string;reason:string;action:string;flood:string;age:number|null}
export interface Domain {
 deriveReading(record:any,now?:number):Reading;
 evaluate(records:any[],watch?:any,now?:number):Evaluation;
 buildFacts(records:any[],watch?:any,now?:number):string[];
 validateCalibration(settings:any):{valid:boolean;errors:string[]};
 syntheticSample(scenario?:string,step?:number,now?:number):any;
 DEFAULT_WATCH:{elevated:number;warning:number;rise_limit:number};
}
declare global {var RiverGuardDomain:Domain;}
