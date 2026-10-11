package main
import (
 "context"; "database/sql"; "encoding/json"; "fmt"; "math/rand"; "os"; "sort"; "sync"; "sync/atomic"; "time"
 mysql "github.com/go-sql-driver/mysql"
)
type Phase struct{Name string; Workers int; Seconds int}
type Stats struct{ Success int64 `json:"success"`; Errors int64 `json:"errors"`; Cancelled int64 `json:"cancelled"`; ByKind map[string]int64 `json:"success_by_kind"`; ErrorKinds map[string]int64 `json:"error_kinds"`; Samples []float64 `json:"-"`; mu sync.Mutex }
var eventID atomic.Int64
var acknowledgedEvents atomic.Int64
func emit(v any){b,_:=json.Marshal(v);fmt.Println(string(b))}
func main(){
 db,e:=sql.Open("mysql","root:111@tcp(127.0.0.1:6001)/mo_stress?timeout=5s&readTimeout=35s&writeTimeout=35s&interpolateParams=true");if e!=nil{panic(e)};defer db.Close();db.SetMaxOpenConns(1100);db.SetMaxIdleConns(1100);db.SetConnMaxLifetime(15*time.Minute)
 phases:=[]Phase{{"baseline",1,30},{"mixed_16",16,60},{"mixed_32",32,90},{"mixed_64",64,120},{"saturation_128",128,180},{"overload_256",256,180},{"analytical_pressure",32,120},{"recovery",4,60}}
 if len(os.Args)>1 && os.Args[1]=="write-pressure"{phases=[]Phase{{"overload_512",512,60},{"overload_1024",1024,60},{"write_pressure_128",128,120},{"write_recovery",4,30}};var prev,n int64;check(db.QueryRow("SELECT COALESCE(MAX(id),0),COUNT(*) FROM events").Scan(&prev,&n));eventID.Store(prev);acknowledgedEvents.Store(n)}
 for _,p:=range phases{run(db,p)}
 ctx,cancel:=context.WithTimeout(context.Background(),2*time.Minute);defer cancel()
 var count,sum,balance,events,distinct int64
 e=db.QueryRowContext(ctx,"SELECT COUNT(*),SUM(id) FROM items").Scan(&count,&sum);check(e)
 e=db.QueryRowContext(ctx,"SELECT SUM(balance) FROM accounts").Scan(&balance);check(e)
 e=db.QueryRowContext(ctx,"SELECT COUNT(*),COUNT(DISTINCT id) FROM events").Scan(&events,&distinct);check(e)
 pass:=count==2000000 && sum==2000001000000 && balance==1000000000 && events==distinct && events>=acknowledgedEvents.Load()
 emit(map[string]any{"type":"integrity","pass":pass,"item_count":count,"item_sum_id":sum,"account_balance_sum":balance,"events":events,"distinct_events":distinct,"acknowledged_events":acknowledgedEvents.Load(),"event_attempts":eventID.Load(),"time":time.Now().UTC()})
 if !pass{os.Exit(2)}
}
func check(e error){if e!=nil{emit(map[string]any{"type":"fatal","error":e.Error()});os.Exit(1)}}
func run(db *sql.DB,p Phase){
 s:=Stats{ByKind:map[string]int64{},ErrorKinds:map[string]int64{}}
 start:=time.Now();ctx,cancel:=context.WithTimeout(context.Background(),time.Duration(p.Seconds)*time.Second);defer cancel()
 emit(map[string]any{"type":"phase_start","phase":p.Name,"workers":p.Workers,"seconds":p.Seconds,"time":start.UTC()})
 var wg sync.WaitGroup
 for w:=0;w<p.Workers;w++{wg.Add(1);go func(worker int){defer wg.Done();rng:=rand.New(rand.NewSource(int64(worker)+start.UnixNano()));for ctx.Err()==nil{
  qctx,qcancel:=context.WithTimeout(ctx,30*time.Second);t:=time.Now();var err error;kind:="lookup";choice:=rng.Intn(100);if p.Name=="analytical_pressure"{choice=99};if p.Name=="write_pressure_128"{choice=50+rng.Intn(40)}
  if choice<50{var v int64;err=db.QueryRowContext(qctx,"SELECT value FROM items WHERE id=?",rng.Intn(2000000)+1).Scan(&v)
  }else if choice<75{kind="transfer";a:=rng.Intn(10000)+1;b:=rng.Intn(10000)+1; if a>b{a,b=b,a};var tx *sql.Tx;tx,err=db.BeginTx(qctx,nil);if err==nil{_,err=tx.ExecContext(qctx,"UPDATE accounts SET balance=balance-1 WHERE id=?",a);if err==nil{_,err=tx.ExecContext(qctx,"UPDATE accounts SET balance=balance+1 WHERE id=?",b)};if err==nil{err=tx.Commit()}else{_ =tx.Rollback()}}
  }else if choice<90{kind="insert";id:=eventID.Add(1);_,err=db.ExecContext(qctx,"INSERT INTO events VALUES (?,?,repeat('e',256))",id,rng.Intn(1000));if err==nil{acknowledgedEvents.Add(1)}
  }else{kind="aggregate";var rows *sql.Rows;rows,err=db.QueryContext(qctx,"SELECT a.grp,COUNT(*),SUM(a.value+b.value) FROM items a JOIN items b ON a.id=b.id GROUP BY a.grp ORDER BY SUM(a.value+b.value) DESC LIMIT 20");if err==nil{for rows.Next(){var grp,n,v int64;if err=rows.Scan(&grp,&n,&v);err!=nil{break};if n!=2000{err=fmt.Errorf("aggregate count integrity: got %d expected 2000",n);break}};if err==nil{err=rows.Err()};rows.Close()}}
  elapsed:=float64(time.Since(t).Microseconds())/1000;qcancel();s.mu.Lock();if err==nil{s.Success++;s.ByKind[kind]++;s.Samples=append(s.Samples,elapsed)}else if ctx.Err()!=nil{s.Cancelled++}else{s.Errors++;key:=kind+": "+err.Error();if me,ok:=err.(*mysql.MySQLError);ok{key=fmt.Sprintf("%s: mysql_%d: %s",kind,me.Number,me.Message)};if len(key)>300{key=key[:300]};s.ErrorKinds[key]++};s.mu.Unlock()
 }}(w)}
 done:=make(chan struct{});go func(){wg.Wait();close(done)}();ticker:=time.NewTicker(10*time.Second);defer ticker.Stop()
loop:for{select{case<-done:break loop;case<-ticker.C:s.mu.Lock();emit(map[string]any{"type":"progress","phase":p.Name,"elapsed_seconds":time.Since(start).Seconds(),"success":s.Success,"errors":s.Errors,"connections":db.Stats().OpenConnections,"in_use":db.Stats().InUse});s.mu.Unlock()}}
 sort.Float64s(s.Samples);pct:=func(f float64)float64{if len(s.Samples)==0{return 0};return s.Samples[int(float64(len(s.Samples)-1)*f)]}
 emit(map[string]any{"type":"phase_end","phase":p.Name,"workers":p.Workers,"elapsed_seconds":time.Since(start).Seconds(),"offered_seconds":p.Seconds,"success_ops_per_second":float64(s.Success)/float64(p.Seconds),"latency_success_ms":map[string]float64{"p50":pct(.5),"p95":pct(.95),"p99":pct(.99),"max":pct(1)},"results":s,"time":time.Now().UTC()})
}
