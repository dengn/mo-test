import test, {before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import mysql from 'mysql2/promise';
import {z} from 'zod';
import {tool as langchainTool} from '@langchain/core/tools';
import {tool as vercelTool} from 'ai';
import {createTool} from '@mastra/core/tools';

const runId=process.env.MO_RUN_ID;
assert.match(runId??'',/^[0-9a-f]{12}$/,'Use run.py to supply an ownership-checked run id');
const cfg={host:process.env.MO_HOST??'127.0.0.1',port:Number(process.env.MO_PORT??6001),user:process.env.MO_USER??'root',password:process.env.MO_PASSWORD??'111',charset:'utf8mb4',connectTimeout:10000};
const database=`ai_reg_${runId}_${crypto.randomBytes(6).toString('hex')}`;
let pool;
function registry(cleaned=false){
  const path=process.env.MO_REGISTRY;
  const value=fs.existsSync(path)?JSON.parse(fs.readFileSync(path,'utf8')):{run_id:runId,databases:[],cleaned:[]};
  assert.equal(value.run_id,runId);
  if(!value.databases.includes(database))value.databases.push(database);
  if(cleaned&&!value.cleaned.includes(database))value.cleaned.push(database);
  fs.writeFileSync(path,JSON.stringify(value,null,2));
}
before(async()=>{
  registry();
  const admin=await mysql.createConnection(cfg);
  try{await admin.query(`CREATE DATABASE \`${database}\``);}finally{await admin.end();}
  pool=mysql.createPool({...cfg,database,connectionLimit:2});
  await pool.query('CREATE TABLE knowledge(id INT PRIMARY KEY,tenant VARCHAR(128),content TEXT,v VECF32(3))');
  await pool.query('INSERT INTO knowledge VALUES(1,?,?,?),(2,?,?,?)',['a','alpha A 中文','[1,0,0]','b','beta B','[0,1,0]']);
});
after(async()=>{
  if(pool)await pool.end();
  const admin=await mysql.createConnection(cfg);
  try{await admin.query(`DROP DATABASE IF EXISTS \`${database}\``);registry(true);}finally{await admin.end();}
});
const schema=z.object({tenant:z.string(),queryText:z.string()});
async function lookup(input){
  const {tenant,queryText}=schema.parse(input);
  const vector=queryText.includes('alpha')?[1,0,0]:[0,1,0];
  const [rows]=await pool.execute({sql:'SELECT id,tenant,content FROM knowledge WHERE tenant=? ORDER BY l2_distance(v,?) LIMIT 1',timeout:10000},[tenant,JSON.stringify(vector)]);
  return rows.map(row=>({...row}));
}
async function verify(invoke){
  for(const [tenant,ids] of [['a',[1]],['b',[2]],['missing',[]],["a' OR 1=1 --",[]]]){
    let result=await invoke({tenant,queryText:'alpha'});
    if(typeof result==='string')result=JSON.parse(result);
    assert.deepEqual(result.map(row=>row.id),ids);
    if(tenant==='a')assert.equal(result[0].content,'alpha A 中文');
  }
}
test('test_langchainjs_structured_tool',async()=>{
  const tool=langchainTool(async input=>JSON.stringify(await lookup(input)),{name:'matrixone_lookup',description:'Retrieve tenant-scoped knowledge',schema});
  await verify(input=>tool.invoke(input));
  await assert.rejects(()=>tool.invoke({tenant:123,queryText:'alpha'}));
});
test('test_vercel_ai_tool_execute',async()=>{
  const tool=vercelTool({description:'Retrieve tenant-scoped knowledge',inputSchema:schema,execute:lookup});
  await verify(input=>tool.execute(input,{toolCallId:'fixture',messages:[]}));
});
test('test_mastra_tool_execute',async()=>{
  const tool=createTool({id:'matrixone_lookup',description:'Retrieve tenant-scoped knowledge',inputSchema:schema,outputSchema:z.array(z.object({id:z.number(),tenant:z.string(),content:z.string()})),execute:lookup});
  await verify(input=>tool.execute(input));
});
