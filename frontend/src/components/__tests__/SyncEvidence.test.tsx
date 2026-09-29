import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SyncEvidence } from '../SyncEvidence';
it.each(['complete','partial','failed','no-op','disabled'] as const)('discloses explicit %s outcome without generic green success',outcome=>{
 render(<SyncEvidence report={{outcome,sections:[{name:'ISA snapshot',status:'checked',checked_at:'2026-09-29T18:30:00Z',valuation_date:'2026-09-01',attempted_at:'2026-09-29T18:29:00Z',coverage_start:'2026-01-01',coverage_end:'2026-09-01'}]}}/>);
 expect(screen.getByText(`Refresh outcome: ${outcome}`)).not.toHaveClass('text-pos');
 expect(screen.getByText(/Checked: 2026-09-29/)).toBeInTheDocument();
 expect(screen.getByText(/Valuation: 2026-09-01/)).toBeInTheDocument();
 expect(screen.getByText(/Attempt: 2026-09-29/)).toBeInTheDocument();
 expect(screen.getByText(/Coverage: 2026-01-01/)).toBeInTheDocument();
});
it('does not infer refreshed valuations from a legacy successful attempt',()=>{render(<SyncEvidence report={{ok:true,steps:[{name:'Broker',status:'ok',detail:null}]}}/>);expect(screen.getByText('Refresh outcome: unreported')).toBeInTheDocument();expect(screen.getByText(/Successful checks do not prove/)).toBeInTheDocument();});
