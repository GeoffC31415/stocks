/** URL builders preserve primary scope/comparison dates; new focus replaces old filters. */
const focusKeys=["inst","instrument_ids","group","group_ids","q","search","category_dimension","category","allocation_dimension","allocation_category","offset"];
function base(search:string,tab:string) {const p=new URLSearchParams(search);p.set("tab",tab);for(const key of focusKeys)p.delete(key);return p;}
function id(value:number):string {if(!Number.isSafeInteger(value)||value<=0)throw new Error("Invalid investigation identifier");return String(value);}
export function holdingsLink(search:string,options:{account?:string;instrumentId?:number;instrumentIds?:number[];groupId?:number;category?:{dimension:string;label:string}}={}) {
 const p=base(search,"holdings");if(options.account)p.set("account",options.account);
 if(options.instrumentId!==undefined)p.set("inst",id(options.instrumentId));
 if(options.instrumentIds){if(!options.instrumentIds.length)throw new Error("Empty constituent selection");p.set("instrument_ids",options.instrumentIds.map(id).join(","));}
 if(options.groupId!==undefined)p.set("group",id(options.groupId));
 if(options.category){p.set("allocation_dimension",options.category.dimension);p.set("allocation_category",options.category.label);}
 return `/portfolio?${p}`;
}

export function ordersLink(search:string,options:{account?:string;instrumentId?:number;groupId?:number;fromDate?:string;toDate?:string;kind?:"all"|"buy"|"sell"|"drip"}={}) {
 const p=base(search,"orders");if(options.account)p.set("account",options.account);p.set("offset","0");
 if(options.instrumentId!==undefined)p.set("inst",id(options.instrumentId));
 if(options.groupId!==undefined)p.set("group_ids",id(options.groupId));
 if(options.fromDate)p.set("from_date",options.fromDate);if(options.toDate)p.set("to_date",options.toDate);
 if(options.kind)p.set("kind",options.kind);
 return `/activity?${p}`;
}
