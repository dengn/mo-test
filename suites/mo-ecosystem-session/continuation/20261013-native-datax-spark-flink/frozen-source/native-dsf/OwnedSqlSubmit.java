import java.nio.file.Files;
import java.nio.file.Paths;
import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;
import org.apache.flink.core.execution.JobClient;
public final class OwnedSqlSubmit {
 public static void main(String[] args) throws Exception {
  if(args.length==1 && args[0].equals("--compile-only")){System.out.println("TABLE_API_CLASSPATH_READY");return;}
  String sql=new String(Files.readAllBytes(Paths.get(args[0])),"UTF-8");
  TableEnvironment t=(TableEnvironment)TableEnvironment.class.getMethod("create",new Class[]{EnvironmentSettings.class}).invoke(null,new Object[]{EnvironmentSettings.newInstance().inStreamingMode().build()});
  int pos=sql.indexOf("EXECUTE STATEMENT SET BEGIN");
  if(pos<0)throw new IllegalArgumentException("Missing native statement set");
  for(String s:sql.substring(0,pos).split(";"))if(!s.trim().isEmpty()) {
   java.util.regex.Matcher m=java.util.regex.Pattern.compile("SET '([^']+)'='([^']*)'",java.util.regex.Pattern.CASE_INSENSITIVE).matcher(s.trim());
   if(m.matches())t.getConfig().getConfiguration().setString(m.group(1),m.group(2));
   else t.executeSql(s.trim());
  }
  TableResult r=t.executeSql(sql.substring(pos).trim());
  JobClient client=(JobClient)r.getJobClient().get();
  System.out.println("NATIVE_JOB_SUBMITTED "+client.getJobID());
 }
}
