// Runtime adapter checks; never presented as SQL execution on MatrixOne.
const fs=require('fs'),path=require('path');
const input=JSON.parse(fs.readFileSync(process.argv[2])),output=process.argv[3];
const root=input.module_root;
const common=require(path.join(root,'@lightdash/common'));
const warehouses=require(path.join(root,'@lightdash/warehouses'));
const version=require(path.join(root,'@lightdash/common/package.json')).version;
if(version!==input.version)throw Error('Lightdash runtime version mismatch');
const records=[];
for(const type of ['mysql','matrixone']){
 for(const kind of ['warehouse','sql-builder']){
  try{
   if(kind==='warehouse')warehouses.warehouseClientFromCredentials({type,...input.credentials,schema:'public',sslmode:'disable'});
   else warehouses.warehouseSqlBuilderFromType(type);
   records.push({id:type+'-'+kind,error:'Adapter is now available: update the integration and execute actual SQL before marking support'});
  }catch(e){records.push({id:type+'-'+kind,error:String(e)});}
 }
}
fs.writeFileSync(output,JSON.stringify({version,warehouse_types:common.WarehouseTypes,records}));
