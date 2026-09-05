import { describe, expect, it } from 'vitest';
import { holdingDisplayName, filterHoldings, parseInstrumentId, sortHoldings } from '../holdingsView';
import type { Instrument } from '../api';
const rows = [{id:1, security_name:'Alpha fund', identifier:'broker-1', ticker:'AAA', account_name:'ISA', group_ids:[2], sector:'Tech', latest_value_gbp:-2}, {id:2, security_name:'Beta', identifier:'broker-2', ticker:'BBB', account_name:'SIPP', group_ids:[], sector:null, latest_value_gbp:null}] as Instrument[];
describe('holdings view', () => {
 it('bounds no-ticker display without changing searchable source identity',()=>{
  const name='A very long original broker security name containing share class and accumulation currency suffix';
  const fund={...rows[0],ticker:null,security_name:name};
  expect(holdingDisplayName(fund).length).toBeLessThanOrEqual(48);
  expect(holdingDisplayName(fund)).toBe('A very long original broker security name…');
  expect(fund.security_name).toBe(name);
  expect(filterHoldings([fund],new URLSearchParams({q:'accumulation currency suffix'})).rows).toEqual([fund]);
 });
 it.each(['constructor','toString','__proto__'])('rejects inherited dimension %s', dimension => {
  const result=filterHoldings(rows,new URLSearchParams({category_dimension:dimension,category:'Unknown'}));
  expect(result.error).toBeTruthy(); expect(result.rows).toEqual([]);
 });
 it('rejects noncanonical and duplicate detail ids', () => {
  for (const raw of ['01','1e2','0','-1','1.0',' 1','9007199254740992','1&inst=2']) expect(parseInstrumentId(new URLSearchParams('inst='+raw))).toBeNull();
  expect(parseInstrumentId(new URLSearchParams('inst=1'))).toBe(1);
 });
 it('searches ticker, source name and identifier and applies explicit filters', () => {
  for(const q of ['AAA','Alpha','broker-1']) expect(filterHoldings(rows,new URLSearchParams({q})).rows.map(i=>i.id)).toEqual([1]);
  expect(filterHoldings(rows,new URLSearchParams('category_dimension=sector&category=Tech&group=2&instrument_ids=1')).rows).toHaveLength(1);
  for(const q of ['instrument_ids=01','group=abc','category_dimension=bad&category=Tech','category=Tech','instrument_ids=1,,2']) {
   expect(filterHoldings(rows,new URLSearchParams(q)).error).toBeTruthy();
   expect(filterHoldings(rows,new URLSearchParams(q)).rows).toEqual([]);
  }
  expect(filterHoldings(rows,new URLSearchParams('category_dimension=sector&category=unknown')).rows).toEqual([]);
 });
 it('keeps missing numeric values last in both directions', () => {
  expect(sortHoldings(rows,'value','asc').map(i=>i.id)).toEqual([1,2]);
  expect(sortHoldings(rows,'value','desc').map(i=>i.id)).toEqual([1,2]);
 });
});
