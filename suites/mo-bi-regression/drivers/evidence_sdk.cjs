// Official native source connector only. No collation monkey patch.
const fs=require('fs'),path=require('path');
const input=JSON.parse(fs.readFileSync(process.argv[2])),output=process.argv[3];
const root=input.module_root;
const mysql=require(path.join(root,'@evidence-dev/mysql'));
const version=require(path.join(root,'@evidence-dev/mysql/package.json')).version;
if(version!==input.version)throw Error('Evidence connector version mismatch');
const creds=input.credentials,opts={...creds,ssl:String(input.ssl)};
(async()=>{
 const records=[];
 for(const c of input.cases){
  try{
   const stream=await mysql(c.sql,opts,100000),rows=[];
   for await(const batch of stream.rows())rows.push(...batch.map(row=>Array.isArray(row)?row:Object.values(row)));
   records.push({id:c.id,rows});
  }catch(e){records.push({id:c.id,error:String(e)});}
 }
 fs.writeFileSync(output,JSON.stringify({version,records}));
})().catch(e=>{process.stderr.write(String(e));process.exitCode=1;});
