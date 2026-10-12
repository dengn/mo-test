"""Verify the published commit/tree and every tracked blob's hash, byte size and Git mode."""
import subprocess,json,hashlib,sys
from pathlib import Path
repo=Path('/workspace/mo-test')
def git(*args):return subprocess.check_output(['git',*args],cwd=repo)
def api(path):return json.loads(subprocess.check_output(['gh','api',path],cwd=repo))
def main():
 commit=git('rev-parse','HEAD').decode().strip();root=git('rev-parse','HEAD^{tree}').decode().strip();remote_commit=api('repos/dengn/mo-test/git/commits/'+commit);assert remote_commit['sha']==commit and remote_commit['tree']['sha']==root
 tree=api('repos/dengn/mo-test/git/trees/'+root+'?recursive=1');assert not tree['truncated'] and tree['sha']==root;remote={r['path']:r for r in tree['tree'] if r['type']=='blob'};local={}
 for record in git('ls-tree','-rlz','HEAD').split(b'\0'):
  if not record:continue
  header,path=record.split(b'\t',1);mode,kind,sha,size=header.decode().split();assert kind=='blob';name=path.decode();data=(repo/name).read_bytes();assert len(data)==int(size);oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert oid==sha;local[name]=dict(mode=mode,sha=sha,size=int(size),sha256=hashlib.sha256(data).hexdigest());r=remote[name];assert (r['mode'],r['sha'],r['size'])==(mode,sha,int(size)),name
 assert set(local)==set(remote)
 result=dict(repository='dengn/mo-test',commit=commit,tree_sha=root,files=len(local),total_bytes=sum(r['size'] for r in local.values()),every_remote_blob_sha_size_mode_matches=True,local_worktree_blob_and_sha256_validated=True,files_sha256={k:v['sha256'] for k,v in local.items()});destination=Path('/workspace/mo-analysis-needs-publication.json');destination.write_text(json.dumps(result,indent=2));print({k:v for k,v in result.items() if k!='files_sha256'})
if __name__=='__main__':main()
