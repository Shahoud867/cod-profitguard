import {describe,it,expect} from 'vitest';
import {money,label,date,number} from './lib';
describe('merchant-facing financial and date presentation',()=>{
 it('converts paisa once and retains negative costs',()=>{expect(money(450000)).toContain('4,500');expect(money(-3500)).toContain('35');expect(money(-3500)).toContain('-');});
 it('shows Pakistan time independently of host timezone',()=>{expect(date('2026-11-08T05:00:00Z')).toMatch(/10:00/);});
 it('preserves operational state meaning',()=>{expect(label('cancelled_before_ship')).toBe('Cancelled Before Ship');expect(number(8000)).toBe('8,000');});
});
