import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SyncEvidence } from '../SyncEvidence';
import publicReport from './fixtures/public-sync-v2.json';

it('renders serialized real public-report evidence without confusing a failed attempt with retained verification', () => {
 render(<SyncEvidence report={publicReport} />);
 expect(screen.getByText('Refresh outcome: partial')).not.toHaveClass('text-pos');
 expect(screen.getByText('Trading 212 / holdings: failed')).toBeInTheDocument();
 expect(screen.getByText('Checked: 2026-09-01T18:30:00+00:00')).toBeInTheDocument();
 expect(screen.getByText('Valuation: 2026-09-01')).toBeInTheDocument();
 expect(screen.getByText('Attempt: 2026-09-29T18:29:00+00:00')).toBeInTheDocument();
 expect(screen.getByText('Coverage: partial')).toBeInTheDocument();
 expect(screen.getByText('Reason: provider_failed')).toBeInTheDocument();
 expect(screen.getByText('Action: retry')).toBeInTheDocument();
 expect(screen.getByText(/retained verified observation/)).toBeInTheDocument();
});
it.each(['complete','partial','failed','no_op','disabled'] as const)('recognizes authoritative %s outcome without inferring green success', outcome => {
 render(<SyncEvidence report={{outcome,ok:true}} />);
 expect(screen.getByText(`Refresh outcome: ${outcome}`)).not.toHaveClass('text-pos');
});
it('uses sanitized step sections when freshness is absent', () => {
 const {freshness: _freshness, ...stepReport} = publicReport;
 render(<SyncEvidence report={stepReport} />);
 expect(screen.getByText('Trading 212 / holdings: failed')).toBeInTheDocument();
 expect(screen.getByText('Checked: 2026-09-01T18:30:00+00:00')).toBeInTheDocument();
});
it('keeps authoritative freshness ahead of duplicate current-run step evidence', () => {
 render(<SyncEvidence report={{...publicReport, steps:[{name:'Trading 212',status:'ok',detail:null,sections:{holdings:{status:'ok'}}}]}} />);
 expect(screen.getAllByText('Trading 212 / holdings: failed')).toHaveLength(1);
 expect(screen.queryByText('Trading 212 / holdings: ok')).not.toBeInTheDocument();
});
it('shows missing verification as unknown even when an attempt and complete outcome exist', () => {
 render(<SyncEvidence report={{outcome:'complete',freshness:{Barclays:{holdings:{last_attempt_at:'2026-09-29T18:29:00+00:00',verified_at:null,valuation_at:null,coverage:'unknown',status:'no_op',reason_code:'not_verified',action_code:'none'}}}}} />);
 expect(screen.getByText('Checked: Not reported')).toBeInTheDocument();
 expect(screen.getByText('Valuation: Not reported')).toBeInTheDocument();
 expect(screen.getByText('Coverage: unknown')).toBeInTheDocument();
});
it('does not infer refreshed valuations from a legacy successful attempt',()=>{
 render(<SyncEvidence report={{ok:true,steps:[{name:'Broker',status:'ok',detail:null}]}}/>);
 expect(screen.getByText('Refresh outcome: unreported')).toBeInTheDocument();
 expect(screen.getByText(/Successful checks do not prove/)).toBeInTheDocument();
});
