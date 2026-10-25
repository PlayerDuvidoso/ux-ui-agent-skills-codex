import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gate, accepts, rejects } from '../helpers/run.mjs';

const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ux-rendered-color-'));
after(()=>fs.rmSync(dir,{recursive:true,force:true}));
function fixture(name,foreground,background='color(srgb 1 1 1)') {
  const file=path.join(dir,name+'.html');
  fs.writeFileSync(file,`<!doctype html><html lang="en"><head><title>Color regression</title><style>
    body {background:${background};}button {background:transparent;color:${foreground};font:16px sans-serif;border:0;padding:12px;}
    </style></head><body><button>Measured text</button></body></html>`);
  return file;
}
for(const script of ['measure_render.mjs','verify_states.mjs']) {
 test(`${script} accepts black on CSS Color 4 white`,()=>{
   const r=gate(script,[fixture(script+'-good','color(srgb 0 0 0)')]);accepts(r);
   assert.doesNotMatch(r.out,/all 0 text|Checked 0 element/);
 });
 test(`${script} still rejects CSS Color 4 low contrast`,()=>{
   rejects(gate(script,[fixture(script+'-bad','color(srgb .8 .8 .8)')]),/need 4.5/);
 });
 test(`${script} measures foreground alpha rather than opaque black`,()=>{
   rejects(gate(script,[fixture(script+'-alpha','color(srgb 0 0 0 / .1)')]),/need 4.5/);
 });
 test(`${script} accepts browser-converted wide gamut black on white`,()=>{
   accepts(gate(script,[fixture(script+'-p3','color(display-p3 0 0 0)')]));
 });
}
