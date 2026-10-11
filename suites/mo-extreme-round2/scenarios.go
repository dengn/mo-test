package main
import("context";"crypto/md5";"database/sql";"encoding/base64";"encoding/hex";"encoding/json";"fmt";"math/rand";"os";"sort";"strconv";"strings";"sync";"sync/atomic";"time"; mysql "github.com/go-sql-driver/mysql")
var db *sql.DB
var journal *os.File
var outMu sync.Mutex
var ackMu sync.Mutex
var ids atomic.Int64
const root="/workspace/mo-extreme-round2/"
func emit(v any){outMu.Lock();defer outMu.Unlock();b,_:=json.Marshal(v);fmt.Println(string(b))}
func must(e error){if e!=nil{emit(map[string]any{"type":"fatal","error":e.Error()});os.Exit(1)}}
func dsn(name string)string{return "root:111@tcp(127.0.0.1:6001)/"+name+"?timeout=3s&readTimeout=20s&writeTimeout=20s&interpolateParams=true"}
func main(){
 nameBytes,e:=os.ReadFile(root+"database.txt");if os.IsNotExist(e){name:="mo_extreme_"+strconv.FormatInt(time.Now().UnixNano(),10);bootstrap,e:=sql.Open("mysql",dsn(""));must(e);_,e=bootstrap.Exec("CREATE DATABASE "+name);must(e);bootstrap.Close();must(os.WriteFile(root+"database.txt",[]byte(name),0600));nameBytes=[]byte(name)}else{must(e)}
 db,e=sql.Open("mysql",dsn(strings.TrimSpace(string(nameBytes))));must(e);defer db.Close();db.SetMaxOpenConns(300);db.SetMaxIdleConns(300)
 mode:="all";if len(os.Args)>1{mode=os.Args[1]}
 journal,e=os.OpenFile(root+"acknowledged.jsonl",os.O_APPEND|os.O_CREATE|os.O_WRONLY,0600);must(e);defer journal.Close()
 if mode=="audit_live"{auditMoney("live",1000);auditBulk("after_active_crash");probe("after_active_crash");return}
 if mode=="resume_live"{
 var top int64;must(db.QueryRow("SELECT COALESCE(MAX(id),0) FROM live_ledger").Scan(&top));raw,e:=os.ReadFile(root+"acknowledged.jsonl");must(e)
 for _,l:=range strings.Split(string(raw),"\n"){if l==""{continue};var v struct{Scenario string `json:"scenario"`;ID int64 `json:"id"`};must(json.Unmarshal([]byte(l),&v));if v.Scenario=="live"&&v.ID>top{top=v.ID}}
 ids.Store(top+1000000)
 label,seconds:="resumed_writers_32",120;if len(os.Args)>2{label="post_fault_writes_32";seconds=30};run(label,32,seconds,func(ctx context.Context,w int,r *rand.Rand)error{a,b:=r.Intn(1000)+1,r.Intn(1000)+1;if a>b{a,b=b,a};e:=transfer(ctx,"live",a,b,false);if e!=nil{time.Sleep(100*time.Millisecond)};return e});auditMoney("live",1000);auditBulk("after_resumed_writes");probe("after_resumed_writes");return
 }
 if mode=="ddl_retry"{
 var stop atomic.Bool;var readers sync.WaitGroup
 for w:=0;w<16;w++{readers.Add(1);go func(w int){defer readers.Done();for !stop.Load(){ctx,c:=context.WithTimeout(context.Background(),5*time.Second);var n int64;_=db.QueryRowContext(ctx,"SELECT COUNT(*) FROM bulk WHERE grp=?",w).Scan(&n);c()}}(w)}
 run("ddl_state_aware_retry",1,60,func(ctx context.Context,w int,r *rand.Rand)error{
 rows,e:=db.QueryContext(ctx,"SHOW COLUMNS FROM bulk LIKE 'transient_column'");if e!=nil{return e};exists:=rows.Next();e=rows.Err();rows.Close();if e!=nil{return e}
 statement:="ALTER TABLE bulk ADD COLUMN transient_column INT DEFAULT 7";if exists{statement="ALTER TABLE bulk DROP COLUMN transient_column"};_,e=db.ExecContext(ctx,statement);return e
 });stop.Store(true);readers.Wait();auditBulk("after_ddl_retry");probe("after_ddl_retry");return
 }
 if mode=="live"{initMoney("live",1000);run("live_restart_writers",32,120,func(ctx context.Context,w int,r *rand.Rand)error{a,b:=r.Intn(1000)+1,r.Intn(1000)+1;if a>b{a,b=b,a};e:=transfer(ctx,"live",a,b,false);if e!=nil{time.Sleep(100*time.Millisecond)};return e});auditMoney("live",1000);return}
 initMoney("hot",2);run("hotspot_128",128,60,func(ctx context.Context,w int,r *rand.Rand)error{return transfer(ctx,"hot",1,2,false)});auditMoney("hot",2);probe("after_hotspot")
 initMoney("dead",2);run("opposite_lock_32",32,45,func(ctx context.Context,w int,r *rand.Rand)error{a,b:=1,2;if w%2==1{a,b=2,1};return transfer(ctx,"dead",a,b,true)});auditMoney("dead",2);probe("after_opposite_lock")
 run("connection_storm_256",256,60,func(ctx context.Context,w int,r *rand.Rand)error{c,e:=sql.Open("mysql",dsn(strings.TrimSpace(string(nameBytes))));if e!=nil{return e};defer c.Close();c.SetMaxOpenConns(1);var v int;return c.QueryRowContext(ctx,"SELECT 1").Scan(&v)});probe("after_connection_storm")
 run("cancel_heavy_queries_32",32,45,func(ctx context.Context,w int,r *rand.Rand)error{c,close:=context.WithTimeout(ctx,100*time.Millisecond);defer close();var n int64;return db.QueryRowContext(c,"SELECT COUNT(*) FROM mo_stress.items a JOIN mo_stress.items b ON a.id=b.id WHERE a.value>=0").Scan(&n)});probe("after_query_cancellation")
 initBulk();seedBulk()
 run("delete_reinsert_16",16,90,func(ctx context.Context,w int,r *rand.Rand)error{block:=(r.Intn(25)*16+w)*500+1;return rewriteBulk(ctx,block,r)});auditBulk("after_delete_reinsert");probe("after_delete_reinsert")
 run("wide_sort_16",16,90,func(ctx context.Context,w int,r *rand.Rand)error{rows,e:=db.QueryContext(ctx,"SELECT id FROM bulk ORDER BY payload LIMIT 100000");if e!=nil{return e};defer rows.Close();for rows.Next(){var id int64;if e=rows.Scan(&id);e!=nil{return e}};return rows.Err()});auditBulk("after_wide_sort");probe("after_wide_sort")
 var stop atomic.Bool;var readers sync.WaitGroup;for w:=0;w<16;w++{readers.Add(1);go func(w int){defer readers.Done();for !stop.Load(){ctx,c:=context.WithTimeout(context.Background(),5*time.Second);var n int64;_ =db.QueryRowContext(ctx,"SELECT COUNT(*) FROM bulk WHERE grp=?",w).Scan(&n);c()}}(w)}
 run("ddl_with_readers",1,60,func(ctx context.Context,w int,r *rand.Rand)error{_,e:=db.ExecContext(ctx,"ALTER TABLE bulk ADD COLUMN transient_column INT DEFAULT 7");if e!=nil{return e};_,e=db.ExecContext(ctx,"ALTER TABLE bulk DROP COLUMN transient_column");return e});stop.Store(true);readers.Wait();auditBulk("after_ddl");probe("after_ddl")
 emit(map[string]any{"type":"suite_complete","time":time.Now().UTC(),"mode":mode})
}
func initMoney(prefix string,n int){_,e:=db.Exec("CREATE TABLE "+prefix+"_money(id BIGINT PRIMARY KEY,balance BIGINT)");must(e);_,e=db.Exec("CREATE TABLE "+prefix+"_ledger(id BIGINT PRIMARY KEY,src BIGINT,dst BIGINT)");must(e);_,e=db.Exec(fmt.Sprintf("INSERT INTO %s_money SELECT result,1000000 FROM generate_series(1,%d) g",prefix,n));must(e)}
func transfer(ctx context.Context,p string,a,b int,delay bool)error{
 tx,e:=db.BeginTx(ctx,nil);if e!=nil{return e};defer tx.Rollback();id:=ids.Add(1)
 if _,e=tx.ExecContext(ctx,"UPDATE "+p+"_money SET balance=balance-1 WHERE id=?",a);e!=nil{return e};if delay{time.Sleep(5*time.Millisecond)}
 if _,e=tx.ExecContext(ctx,"UPDATE "+p+"_money SET balance=balance+1 WHERE id=?",b);e!=nil{return e}
 if _,e=tx.ExecContext(ctx,"INSERT INTO "+p+"_ledger VALUES(?,?,?)",id,a,b);e!=nil{return e};if e=tx.Commit();e!=nil{return e}
 ackMu.Lock();_,e=fmt.Fprintf(journal,"{\"scenario\":%q,\"id\":%d}\n",p,id);ackMu.Unlock();return e
}
func auditMoney(p string,n int){
 ctx,c:=context.WithTimeout(context.Background(),90*time.Second);defer c();expected:=make(map[int64]int64);for i:=1;i<=n;i++{expected[int64(i)]=1000000}
 committed:=make(map[int64]bool);rows,e:=db.QueryContext(ctx,"SELECT id,src,dst FROM "+p+"_ledger");if e!=nil{emit(map[string]any{"type":"audit","scenario":p,"pass":false,"error":e.Error()});return};for rows.Next(){var id,a,b int64;must(rows.Scan(&id,&a,&b));expected[a]--;expected[b]++;committed[id]=true};e=rows.Err();rows.Close();must(e)
 rows,e=db.QueryContext(ctx,"SELECT id,balance FROM "+p+"_money");must(e);good:=true;var total,count int64;for rows.Next(){var id,v int64;must(rows.Scan(&id,&v));total+=v;count++;if expected[id]!=v{good=false}};must(rows.Err());rows.Close()
 must(journal.Sync());raw,e:=os.ReadFile(root+"acknowledged.jsonl");must(e);acks,missing:=0,0;for _,l:=range strings.Split(string(raw),"\n"){if l==""{continue};var v struct{Scenario string `json:"scenario"`;ID int64 `json:"id"`};must(json.Unmarshal([]byte(l),&v));if v.Scenario==p{acks++;if !committed[v.ID]{missing++}}}
 emit(map[string]any{"type":"audit","scenario":p,"pass":good&&count==int64(n)&&total==int64(n)*1000000&&missing==0,"account_count":count,"balance_sum":total,"ledger_rows":len(committed),"acknowledged_transactions":acks,"missing_acknowledged_ids":missing,"balances_match_ledger":good,"time":time.Now().UTC()})
}
func initBulk(){_,e:=db.Exec("CREATE TABLE bulk(id BIGINT PRIMARY KEY,grp INT,payload VARCHAR(2048),digest CHAR(32))");must(e)}
func makeInsert(low int,r *rand.Rand)(string,[]any){s:="INSERT INTO bulk VALUES ";args:=make([]any,0,2000);bytes:=make([]byte,1536);for j:=0;j<500;j++{if j>0{s+=","};s+="(?,?,?,?)";r.Read(bytes);payload:=base64.StdEncoding.EncodeToString(bytes);h:=md5.Sum([]byte(payload));args=append(args,low+j,(low+j)%1000,payload,hex.EncodeToString(h[:]))};return s,args}
func seedBulk(){t:=time.Now();var wg sync.WaitGroup;errch:=make(chan error,8);for w:=0;w<8;w++{wg.Add(1);go func(w int){defer wg.Done();r:=rand.New(rand.NewSource(int64(w)+333));for block:=w;block<400;block+=8{ctx,c:=context.WithTimeout(context.Background(),30*time.Second);s,args:=makeInsert(block*500+1,r);_,e:=db.ExecContext(ctx,s,args...);c();if e!=nil{errch<-e;return}}}(w)};wg.Wait();close(errch);for e:=range errch{must(e)};emit(map[string]any{"type":"seed","rows":200000,"logical_payload_bytes":409600000,"elapsed_seconds":time.Since(t).Seconds(),"payload":"independent pseudorandom 1536 bytes encoded as base64 (2048 chars)"});auditBulk("after_seed")}
func rewriteBulk(ctx context.Context,low int,r *rand.Rand)error{tx,e:=db.BeginTx(ctx,nil);if e!=nil{return e};defer tx.Rollback();_,e=tx.ExecContext(ctx,"DELETE FROM bulk WHERE id BETWEEN ? AND ?",low,low+499);if e!=nil{return e};s,args:=makeInsert(low,r);if _,e=tx.ExecContext(ctx,s,args...);e!=nil{return e};return tx.Commit()}
func auditBulk(name string){ctx,c:=context.WithTimeout(context.Background(),90*time.Second);defer c();var count,sum,bad,length int64;e:=db.QueryRowContext(ctx,"SELECT COUNT(*),SUM(id),SUM(CASE WHEN md5(payload)<>digest THEN 1 ELSE 0 END),SUM(length(payload)) FROM bulk").Scan(&count,&sum,&bad,&length);good:=e==nil&&count==200000&&sum==20000100000&&bad==0&&length==409600000;emit(map[string]any{"type":"audit","scenario":name,"pass":good,"rows":count,"sum_id":sum,"bad_digest_rows":bad,"payload_bytes":length,"error":fmt.Sprint(e),"time":time.Now().UTC()})}
func probe(name string){t:=time.Now();ctx,c:=context.WithTimeout(context.Background(),30*time.Second);defer c();lat:=[]float64{};for i:=0;i<100;i++{s:=time.Now();var n int;e:=db.QueryRowContext(ctx,"SELECT 1").Scan(&n);if e!=nil{emit(map[string]any{"type":"probe","scenario":name,"pass":false,"error":e.Error()});return};lat=append(lat,float64(time.Since(s).Microseconds())/1000)};sort.Float64s(lat);emit(map[string]any{"type":"probe","scenario":name,"pass":true,"queries":100,"p99_ms":lat[98],"max_ms":lat[99],"elapsed_seconds":time.Since(t).Seconds(),"time":time.Now().UTC()})}
func run(name string,workers,seconds int,fn func(context.Context,int,*rand.Rand)error){
 start:=time.Now();ctx,c:=context.WithTimeout(context.Background(),time.Duration(seconds)*time.Second);defer c();emit(map[string]any{"type":"scenario_start","scenario":name,"workers":workers,"seconds":seconds,"time":start.UTC()});var mu sync.Mutex;success,errors,cancelled:=int64(0),int64(0),int64(0);kinds:=map[string]int64{};samples:=[]float64{};var wg sync.WaitGroup
 for w:=0;w<workers;w++{wg.Add(1);go func(w int){defer wg.Done();r:=rand.New(rand.NewSource(start.UnixNano()+int64(w)));for ctx.Err()==nil{q,qc:=context.WithTimeout(ctx,15*time.Second);t:=time.Now();e:=fn(q,w,r);elapsed:=float64(time.Since(t).Microseconds())/1000;qc();mu.Lock();samples=append(samples,elapsed);if e==nil{success++}else if ctx.Err()!=nil{cancelled++}else{errors++;key:=e.Error();if me,ok:=e.(*mysql.MySQLError);ok{key=fmt.Sprintf("mysql_%d: %s",me.Number,me.Message)};if strings.Contains(key,"context deadline exceeded"){key="context deadline exceeded"};if strings.Contains(key,"conflict"){key="transaction conflict"};if strings.Contains(key,"deadlock"){key="deadlock detected"};if strings.Contains(key,"connection refused"){key="connection refused"};if strings.Contains(key,"invalid connection"){key="invalid connection"};if strings.Contains(key,"EOF"){key="EOF"};if len(key)>220{key=key[:220]};kinds[key]++};mu.Unlock()}}(w)}
 done:=make(chan struct{});go func(){wg.Wait();close(done)}();tick:=time.NewTicker(10*time.Second);defer tick.Stop()
 loop:for{select{case<-done:break loop;case<-tick.C:mu.Lock();emit(map[string]any{"type":"progress","scenario":name,"elapsed_seconds":time.Since(start).Seconds(),"success":success,"errors":errors,"in_use":db.Stats().InUse});mu.Unlock()}}
 sort.Float64s(samples);pct:=func(f float64)float64{if len(samples)==0{return 0};return samples[int(float64(len(samples)-1)*f)]};emit(map[string]any{"type":"scenario_end","scenario":name,"workers":workers,"offered_seconds":seconds,"elapsed_seconds":time.Since(start).Seconds(),"success":success,"errors":errors,"teardown_cancelled":cancelled,"success_ops_per_second":float64(success)/float64(seconds),"latency_all_attempts_ms":map[string]float64{"p50":pct(.5),"p95":pct(.95),"p99":pct(.99),"max":pct(1)},"error_kinds":kinds,"time":time.Now().UTC()})
}
