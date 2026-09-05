import type { Instrument } from './api';
export type HoldingSort = 'security' | 'account' | 'value' | 'weight' | 'pnl' | 'delta';
export const holdingSorts: HoldingSort[] = ['security','account','value','weight','pnl','delta'];
const strictId = (raw: string | null): number | null => raw && /^[1-9][0-9]*$/.test(raw) && Number.isSafeInteger(Number(raw)) ? Number(raw) : null;
export const parseInstrumentId = (params: URLSearchParams): number | null => params.getAll('inst').length === 1 ? strictId(params.get('inst')) : null;
export const holdingDisplayName = (i: Instrument) => {
 const name = i.ticker || i.security_name || i.identifier;
 if (name.length <= 48) return name;
 const prefix = name.slice(0,47);
 const boundary = prefix.search(/\s+\S*$/);
 return (boundary > 0 ? prefix.slice(0,boundary) : prefix).trimEnd() + '…';
};
export function filterHoldings(instruments: Instrument[], params: URLSearchParams): { rows: Instrument[]; error: string | null } {
 const invalid = {rows: [], error: 'Invalid holdings filter. Correct or clear the URL filters.'};
 for(const key of ['q','category_dimension','category','group','instrument_ids']) if(params.getAll(key).length > 1) return invalid;
 const dimension = params.get('category_dimension');
 const category = params.get('category');
 const fields = {asset_class:'asset_class',sector:'sector',region:'region',account:'account_name'} as const;
 if ((dimension !== null || category !== null) && (!dimension || !Object.prototype.hasOwnProperty.call(fields, dimension) || !category)) return invalid;
 const group = params.has('group') ? strictId(params.get('group')) : null;
 if(params.has('group') && group === null) return invalid;
 const ids = params.has('instrument_ids') ? params.get('instrument_ids')!.split(',').map(strictId) : null;
 if(ids && (ids.some(id=>id === null) || new Set(ids).size !== ids.length)) return invalid;
 const q = (params.get('q') ?? '').toLowerCase().trim();
 return { error:null, rows: instruments.filter(i => {
  if(q && ![i.ticker,i.security_name,i.identifier,String(i.id)].some(s=>s?.toLowerCase().includes(q))) return false;
  if(group !== null && !i.group_ids.includes(group)) return false;
  if(ids && !ids.includes(i.id)) return false;
  if(dimension && category) {
   const value = i[fields[dimension as keyof typeof fields]] ?? 'Unknown';
   if(value !== category) return false;
  }
  return true;
 })};
}
export function sortHoldings(rows: Instrument[], sort: HoldingSort, direction: 'asc'|'desc') {
 const value = (i: Instrument): string|number|null => sort === 'security' ? holdingDisplayName(i) : sort === 'account' ? i.account_name : sort === 'pnl' ? i.pnl_gbp : sort === 'delta' ? i.delta_value_gbp_since_prev_snapshot : i.latest_value_gbp;
 return [...rows].sort((a,b) => {
  const av=value(a), bv=value(b);
  if(av == null) return bv == null ? a.id-b.id : 1;
  if(bv == null) return -1;
  const comparison = typeof av === 'string' && typeof bv === 'string' ? av.localeCompare(bv) : Number(av)-Number(bv);
  return comparison * (direction === 'asc' ? 1 : -1) || a.id-b.id;
 });
}
