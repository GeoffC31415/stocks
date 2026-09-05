import { afterEach, expect, it, vi } from 'vitest';
import { api } from '../api';
afterEach(()=>vi.unstubAllGlobals());
it('requests authoritative account-scoped group performance',async()=>{const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>[]});vi.stubGlobal('fetch',fetcher);await api.getGroupPerformance(1000,'ISA & savings');expect(String(fetcher.mock.calls[0][0])).toContain('account_name=ISA+%26+savings');});
